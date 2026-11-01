"""Команды обслуживания: python -m app.cli <команда>.

  migrate              миграции + справочники (+ демо-данные при DEMO_DATA=true) + первичный администратор
  demo-data            загрузить демонстрационные данные в пустые разделы
  create-admin LOGIN   создать администратора (пароль спрашивается или берётся из ADMIN_PASSWORD)
  reset-password LOGIN сбросить пароль пользователя (выдаётся временный)
  check-schema         проверить, что схема базы актуальна (код выхода 1, если нет)
  cleanup-sessions     удалить истёкшие сессии
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
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
