"""Команды обслуживания: python -m app.cli <команда>.

  migrate              миграции + справочники (+ демо-данные при DEMO_DATA=true) + первичный администратор
  demo-data            загрузить демонстрационные данные в пустые разделы
  create-admin LOGIN   создать администратора (пароль спрашивается или берётся из ADMIN_PASSWORD)
  reset-password LOGIN сбросить пароль пользователя (выдаётся временный)
  check-schema         проверить, что схема базы актуальна (код выхода 1, если нет)
  cleanup-sessions     удалить истёкшие сессии
  org-sync --ad        синхронизация структуры с Active Directory (по умолчанию — только план;
                       --apply применить, --create-missing создавать новых, --deactivate-missing
                       отключать пропавших из каталога, --json полный план); --csv ФАЙЛ — загрузка списком.
                       Код выхода: 0 — готово, 1 — в плане ошибки (ничего не записано), 2 — каталог
                       или файл недоступны
"""
from __future__ import annotations

import argparse
import getpass
import logging
import sys

from sqlalchemy import delete, select

from .core.config import settings
from .core.db import engine, session_scope, utcnow
from .core.logging import configure_logging
from .core.security import generate_password, hash_password

log = logging.getLogger("app.cli")


def cmd_migrate(_args) -> int:
    from .core.migrate import upgrade
    from .services.demo_data import load_demo_data
    from .services.reference_data import ensure_initial_admin, sync_reference_data

    upgrade()
    with session_scope() as db:
        sync_reference_data(db)
        if settings.demo_data:
            load_demo_data(db)
        ensure_initial_admin(db)
    return 0


def cmd_demo_data(_args) -> int:
    from .services.demo_data import load_demo_data
    from .services.reference_data import sync_reference_data

    with session_scope() as db:
        sync_reference_data(db)
        load_demo_data(db)
    return 0


def cmd_create_admin(args) -> int:
    from .models import User

    password = settings.admin_password or getpass.getpass("Пароль: ")
    if len(password) < settings.password_min_length:
        print(f"Пароль короче {settings.password_min_length} символов", file=sys.stderr)
        return 1
    with session_scope() as db:
        if db.scalar(select(User).where(User.username == args.username)):
            print(f"Пользователь «{args.username}» уже существует", file=sys.stderr)
            return 1
        db.add(User(username=args.username, full_name=args.full_name or args.username, role="admin",
                    password_hash=hash_password(password), must_change_password=True,
                    password_changed_at=utcnow()))
    print(f"Администратор «{args.username}» создан; при первом входе потребуется сменить пароль")
    return 0


def cmd_reset_password(args) -> int:
    from .models import User, UserSession

    password = generate_password()
    with session_scope() as db:
        user = db.scalar(select(User).where(User.username == args.username))
        if not user:
            print(f"Пользователь «{args.username}» не найден", file=sys.stderr)
            return 1
        user.password_hash = hash_password(password)
        user.must_change_password = True
        user.is_active = True
        user.password_changed_at = utcnow()
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    print(f"Временный пароль для «{args.username}»: {password}")
    return 0


def cmd_check_schema(_args) -> int:
    from .core.migrate import check_schema_is_current

    with engine.connect() as conn:
        ok, current, head = check_schema_is_current(conn)
    print(f"Схема: {current or 'нет'}; актуальная: {head}")
    return 0 if ok else 1


def cmd_cleanup_sessions(_args) -> int:
    from .services.sessions import purge_expired

    with session_scope() as db:
        removed = purge_expired(db)
    print(f"Удалено истёкших сессий: {removed}")
    return 0


def _print_plan(result: dict) -> None:
    summary = result["summary"]
    print(f"Строк: {summary['rows']}; создать подразделений: {summary['create_departments']}; "
          f"создать сотрудников: {summary['create_users']}; изменить: {summary['update_users']}; "
          f"без изменений: {summary['unchanged']}; отключить: {summary['deactivate_users']}; "
          f"ошибок: {summary['errors']}")
    for user in result["users"]:
        if user["errors"]:
            print(f"  строка {user['line']}: {user['email'] or user['name']}: {'; '.join(user['errors'])}")


def cmd_org_sync(args) -> int:
    import json
    from pathlib import Path

    from .core import db as core_db
    from .core.errors import AppError
    from .models import User
    from .services import ad_sync, org_import

    try:
        if args.ad:
            rows, refs = ad_sync.load_rows()
            options = {"source": "ad", "manager_refs": refs, "deactivate_missing": args.deactivate_missing}
        else:
            rows = org_import.parse_upload(args.csv, Path(args.csv).read_bytes())
            options = {"source": "csv"}
    except (AppError, OSError) as exc:
        print(f"Ошибка: {getattr(exc, 'detail', exc)}", file=sys.stderr)
        return 2
    options["create_missing"] = args.create_missing
    db = core_db.SessionLocal()
    try:
        actor = db.scalar(select(User).where(User.username == args.actor)) if args.actor else None
        if args.actor and actor is None:
            print(f"Пользователь «{args.actor}» не найден", file=sys.stderr)
            return 2
        if args.apply:
            result, applied = org_import.apply_import(db, actor, rows, **options)
            if applied:
                db.commit()
            else:
                db.rollback()
        else:
            result = {**org_import.plan_import(db, rows, actor_id=actor.id if actor else None, **options).as_dict(),
                      "applied": False}
            db.rollback()
    finally:
        db.close()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        _print_plan(result)
    if not result["can_apply"]:
        print("Не применено: исправьте ошибки" if args.apply else "В плане есть ошибки", file=sys.stderr)
        return 1
    if args.apply:
        print("Изменения применены")
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Обслуживание «Дашбордов компании»")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate").set_defaults(func=cmd_migrate)
    sub.add_parser("demo-data").set_defaults(func=cmd_demo_data)
    p = sub.add_parser("create-admin")
    p.add_argument("username")
    p.add_argument("--full-name", default="")
    p.set_defaults(func=cmd_create_admin)
    p = sub.add_parser("reset-password")
    p.add_argument("username")
    p.set_defaults(func=cmd_reset_password)
    sub.add_parser("check-schema").set_defaults(func=cmd_check_schema)
    sub.add_parser("cleanup-sessions").set_defaults(func=cmd_cleanup_sessions)
    p = sub.add_parser("org-sync", help="синхронизация структуры с AD или загрузка списком")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--ad", action="store_true", help="читать сотрудников из Active Directory (AD_SYNC_*)")
    source.add_argument("--csv", metavar="ФАЙЛ", help="загрузить список (.csv или .xlsx)")
    p.add_argument("--apply", action="store_true", help="применить план (по умолчанию — только показать)")
    p.add_argument("--create-missing", action="store_true", help="создавать сотрудников, которых ещё нет")
    p.add_argument("--deactivate-missing", action="store_true",
                   help="только AD: отключить пришедших из AD, которых нет в каталоге")
    p.add_argument("--actor", default=None, help="логин, от имени которого записывается журнал")
    p.add_argument("--json", action="store_true", help="вывести полный план в JSON")
    p.set_defaults(func=cmd_org_sync)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
