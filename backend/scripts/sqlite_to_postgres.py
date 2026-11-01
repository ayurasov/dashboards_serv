"""Перенос данных из базы SQLite (схема 0.1.0) в PostgreSQL.

    DATABASE_URL=postgresql+psycopg://… python scripts/sqlite_to_postgres.py /path/to/source.db [--force]

Обе базы должны быть на одной ревизии схемы (сначала `python -m app.cli migrate` для каждой).
Таблицы PostgreSQL очищаются и заполняются строками из SQLite; последовательности
идентификаторов выставляются после последних строк. Если в PostgreSQL уже есть данные служб,
скрипт откажется работать без --force.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, func, select, text  # noqa: E402

from app import models  # noqa: E402,F401
from app.core.config import settings  # noqa: E402
from app.core.db import Base  # noqa: E402
from app.core.migrate import current_revision  # noqa: E402

GUARD_TABLES = ("hr_months", "tp_weekly_reports", "naumen_tickets", "partnerships")
BATCH = 2000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", help="файл базы SQLite")
    parser.add_argument("--force", action="store_true", help="перезаписать данные в PostgreSQL")
    args = parser.parse_args()

    if not settings.database_url.startswith("postgresql"):
        print("DATABASE_URL должен указывать на PostgreSQL", file=sys.stderr)
        return 2
    source = create_engine(f"sqlite:///{Path(args.source).resolve()}")
    target = create_engine(settings.database_url)

    with source.connect() as src, target.connect() as dst:
        if current_revision(src) != current_revision(dst):
            print(f"Ревизии схем различаются: SQLite {current_revision(src)}, PostgreSQL {current_revision(dst)}. "
                  "Выполните python -m app.cli migrate для обеих баз.", file=sys.stderr)
            return 2
        if not args.force:
            for name in GUARD_TABLES:
                table = Base.metadata.tables[name]
                if dst.execute(select(func.count()).select_from(table)).scalar():
                    print(f"В PostgreSQL уже есть данные ({name}). Запустите с --force, чтобы заменить их.",
                          file=sys.stderr)
                    return 3

    tables = Base.metadata.sorted_tables
    with target.begin() as dst:
        names = ", ".join(f'"{t.name}"' for t in tables)
        dst.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
        with source.connect() as src:
            for table in tables:
                rows = [dict(r._mapping) for r in src.execute(select(table))]
                for i in range(0, len(rows), BATCH):
                    dst.execute(table.insert(), rows[i:i + BATCH])
                print(f"{table.name}: {len(rows)}")
        for table in tables:
            pk = list(table.primary_key.columns)
            if len(pk) == 1 and pk[0].autoincrement and pk[0].type.python_type is int:
                column = pk[0].name
                dst.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('\"{table.name}\"', '{column}'), "
                    f"COALESCE((SELECT MAX({column}) FROM \"{table.name}\"), 1), "
                    f"(SELECT MAX({column}) FROM \"{table.name}\") IS NOT NULL)"))
    print("Готово: данные перенесены")
    return 0


if __name__ == "__main__":
    sys.exit(main())
