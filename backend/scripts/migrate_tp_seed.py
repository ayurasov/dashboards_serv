#!/usr/bin/env python3
"""
Миграция данных из tp-report/seed_data.json в основную БД dashboards_serv.

Запуск:
    cd /path/to/dashboards_serv
    python backend/scripts/migrate_tp_seed.py

Предварительно:
    1. Выполните alembic upgrade head (таблица tp_report_rows должна существовать)
    2. Запустите скрипт из корня репозитория
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

SEED_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'tp-report', 'seed_data.json')

DATA_COLUMNS = [
    "year","week","total_in_work","avail_total","rushydro_hours","transneft_hours",
    "roscosmos_hours","bryansk_hours","mchs_hours","internal_sales_hours","new_received","renewed",
    "ratio_solved_received","altos_rusg_email","altos_rusg_tf","altos_other_email","altos_other_tf",
    "altoffice_rusg_email","altoffice_rusg_tf","altoffice_other_email","altoffice_other_tf",
    "projserver_taken","total_solved_week","altos_avg_time","altos_total","altos_1_2line","altos_3line",
    "altoffice_avg_time","altoffice_total","altoffice_1_2line","altoffice_3line","projserver_solved",
    "altos_avail_total","altos_avail_1_3","altos_avail_4_7","altos_avail_8_10","altoffice_avail_total",
    "altoffice_avail_1_3","altoffice_avail_4_7","altoffice_avail_8_10","projserver_avail","extra","period"
]

def main():
    try:
        from backend.app.database import SessionLocal
        from backend.app.models import TpReportRow
    except ImportError:
        # fallback: direct SQLite
        import sqlite3, pathlib
        db_path = pathlib.Path(__file__).parent.parent / 'hr_dashboard.db'
        if not db_path.exists():
            print(f'[ERROR] DB not found at {db_path}')
            sys.exit(1)
        conn = sqlite3.connect(db_path)
        _migrate_sqlite(conn)
        conn.close()
        return

    if not os.path.exists(SEED_PATH):
        print(f'[ERROR] seed_data.json not found at {SEED_PATH}')
        sys.exit(1)

    with open(SEED_PATH, encoding='utf-8') as f:
        seed = json.load(f)

    db = SessionLocal()
    try:
        existing = db.query(TpReportRow).count()
        if existing > 0:
            ans = input(f'В таблице уже {existing} строк. Перезаписать? [y/N] ')
            if ans.strip().lower() != 'y':
                print('Отмена.')
                return
            db.query(TpReportRow).delete()

        for row in seed:
            obj = TpReportRow(**{c: row.get(c) for c in DATA_COLUMNS})
            db.add(obj)
        db.commit()
        print(f'[OK] Импортировано {len(seed)} строк.')
    finally:
        db.close()


def _migrate_sqlite(conn):
    """Прямая запись через sqlite3 (fallback если SQLAlchemy не настроен)."""
    if not os.path.exists(SEED_PATH):
        print(f'[ERROR] {SEED_PATH} not found'); sys.exit(1)
    with open(SEED_PATH, encoding='utf-8') as f:
        seed = json.load(f)
    cur = conn.execute('SELECT COUNT(*) FROM tp_report_rows')
    existing = cur.fetchone()[0]
    if existing > 0:
        ans = input(f'В таблице уже {existing} строк. Перезаписать? [y/N] ')
        if ans.strip().lower() != 'y': print('Отмена.'); return
        conn.execute('DELETE FROM tp_report_rows')
    col_names    = ', '.join(f'"{c}"' for c in DATA_COLUMNS)
    placeholders = ', '.join(['?'] * len(DATA_COLUMNS))
    for row in seed:
        vals = [row.get(c) for c in DATA_COLUMNS]
        conn.execute(f'INSERT INTO tp_report_rows ({col_names}) VALUES ({placeholders})', vals)
    conn.commit()
    print(f'[OK] Импортировано {len(seed)} строк (sqlite fallback).')


if __name__ == '__main__':
    main()
