"""Database engine and session."""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings, db_connect_args

engine = create_engine(
    settings.database_url,
    connect_args=db_connect_args(),
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


# create_all() never alters existing tables, so columns added to a model after a
# database was first created have to be filled in by hand.
ADDED_COLUMNS = {
    "users": [("phone", "VARCHAR(50)"), ("avatar", "TEXT"), ("position", "VARCHAR(200)")],
    "benchmarks": [("target_value", "FLOAT"), ("description", "TEXT"), ("source", "VARCHAR(300)")],
}


def ensure_added_columns():
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl_type in columns:
                if name not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
