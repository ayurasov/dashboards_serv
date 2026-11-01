"""Интеграции и входящие данные (версия 0.4.0, ADR-0011).

- integrations — подключения к внешним системам: вид коннектора, настройки (JSON без секретов),
  секреты (зашифрованы ключом, производным от SECRET_KEY) и адрес, к которому они привязаны,
  расписание, состояние коннектора, отметки проверки и здоровья;
- integration_runs — журнал запусков (повод, итог, счётчики, ошибка);
- inbound_keys — ключи для входящих вызовов (SHA-256 и префикс, область, отзыв);
- inbox_items — элементы входящих: источник, файл (содержимое до срока хранения), SHA-256, набор,
  статус, план и итог (и краткая сводка для списка); частичный уникальный индекс (набор, SHA-256) по «живым» элементам
  распознаёт повтор файла;
- inbox_rules — «применять сразу» для источника и набора.

Откат удаляет таблицы и снимает новые полномочия data.manage и integrations.manage
(в 0.3.0 их нет — иначе 0.3.0 отклоняла бы изменение полномочий таких пользователей).

Revision ID: 0016_integrations
Revises: 0015_reports
"""
import sqlalchemy as sa
from alembic import op

revision = "0016_integrations"
down_revision = "0015_reports"
branch_labels = None
depends_on = None

BIG_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
LIVE = sa.text("status IN ('received', 'recognized', 'pending', 'applied')")
NEW_CAPABILITIES = ("data.manage", "integrations.manage")


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=True),
        sa.Column("secret_bound_url", sa.String(500), nullable=True),
        sa.Column("schedule", sa.JSON(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("running_since", sa.DateTime(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_ok_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_integrations"),
        sa.UniqueConstraint("name", name="uq_integrations_name"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_integrations_created_by_id_users",
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], name="fk_integrations_updated_by_id_users",
                                ondelete="SET NULL"),
    )
    op.create_index("ix_integrations_kind", "integrations", ["kind"])
    op.create_index("ix_integrations_next_run_at", "integrations", ["next_run_at"])

    op.create_table(
        "integration_runs",
        sa.Column("id", BIG_ID, nullable=False),
        sa.Column("integration_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_integration_runs"),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"],
                                name="fk_integration_runs_integration_id_integrations", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_integration_runs_user_id_users",
                                ondelete="SET NULL"),
        sa.CheckConstraint("trigger IN ('manual', 'schedule', 'webhook', 'folder', 'cli')",
                           name="ck_integration_runs_trigger"),
        sa.CheckConstraint("status IN ('running', 'ok', 'partial', 'error')", name="ck_integration_runs_status"),
    )
    op.create_index("ix_integration_runs_integration_id_started_at", "integration_runs",
                    ["integration_id", "started_at"])

    op.create_table(
        "inbound_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("issued_by_id", sa.Integer(), nullable=True),
        sa.Column("issued_by", sa.String(100), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_inbound_keys"),
        sa.UniqueConstraint("sha256", name="uq_inbound_keys_sha256"),
        sa.ForeignKeyConstraint(["issued_by_id"], ["users.id"], name="fk_inbound_keys_issued_by_id_users",
                                ondelete="SET NULL"),
    )

    op.create_table(
        "inbox_items",
        sa.Column("id", BIG_ID, nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("source_ref", sa.String(500), nullable=False),
        sa.Column("integration_id", sa.Integer(), nullable=True),
        sa.Column("inbound_key_id", sa.Integer(), nullable=True),
        sa.Column("filename", sa.String(300), nullable=False),
        sa.Column("content_type", sa.String(200), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("dataset", sa.String(40), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("plan_ok", sa.Boolean(), nullable=True),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("duplicate_of_id", BIG_ID, nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("received_by_id", sa.Integer(), nullable=True),
        sa.Column("received_by", sa.String(100), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("applied_by_id", sa.Integer(), nullable=True),
        sa.Column("applied_by", sa.String(100), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=True),
        sa.Column("content_purged_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_inbox_items"),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"],
                                name="fk_inbox_items_integration_id_integrations", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["inbound_key_id"], ["inbound_keys.id"],
                                name="fk_inbox_items_inbound_key_id_inbound_keys", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["duplicate_of_id"], ["inbox_items.id"],
                                name="fk_inbox_items_duplicate_of_id_inbox_items", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["received_by_id"], ["users.id"], name="fk_inbox_items_received_by_id_users",
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["applied_by_id"], ["users.id"], name="fk_inbox_items_applied_by_id_users",
                                ondelete="SET NULL"),
        sa.CheckConstraint("source IN ('folder', 'upload', 'api', 'integration')", name="ck_inbox_items_source"),
        sa.CheckConstraint("status IN ('received', 'recognized', 'pending', 'applied', 'rejected', 'error', "
                           "'duplicate')", name="ck_inbox_items_status"),
    )
    op.create_index("ix_inbox_items_integration_id", "inbox_items", ["integration_id"])
    op.create_index("ix_inbox_items_inbound_key_id", "inbox_items", ["inbound_key_id"])
    op.create_index("ix_inbox_items_sha256", "inbox_items", ["sha256"])
    op.create_index("ix_inbox_items_dataset", "inbox_items", ["dataset"])
    op.create_index("ix_inbox_items_status", "inbox_items", ["status"])
    op.create_index("ix_inbox_items_received_at", "inbox_items", ["received_at"])
    op.create_index("uq_inbox_items_dataset_sha256", "inbox_items", ["dataset", "sha256"], unique=True,
                    sqlite_where=LIVE, postgresql_where=LIVE)

    op.create_table(
        "inbox_rules",
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("dataset", sa.String(40), nullable=False),
        sa.Column("auto_apply", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("source", "dataset", name="pk_inbox_rules"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], name="fk_inbox_rules_updated_by_id_users",
                                ondelete="SET NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    users = sa.table("users", sa.column("id", sa.Integer), sa.column("capabilities", sa.JSON))
    for row in bind.execute(sa.select(users.c.id, users.c.capabilities)).all():
        caps = list(row.capabilities or [])
        if any(c in NEW_CAPABILITIES for c in caps):
            bind.execute(users.update().where(users.c.id == row.id)
                         .values(capabilities=[c for c in caps if c not in NEW_CAPABILITIES]))
    op.drop_table("inbox_rules")
    op.drop_index("uq_inbox_items_dataset_sha256", table_name="inbox_items")
    for column in ("received_at", "status", "dataset", "sha256", "inbound_key_id", "integration_id"):
        op.drop_index(f"ix_inbox_items_{column}", table_name="inbox_items")
    op.drop_table("inbox_items")
    op.drop_table("inbound_keys")
    op.drop_index("ix_integration_runs_integration_id_started_at", table_name="integration_runs")
    op.drop_table("integration_runs")
    op.drop_index("ix_integrations_next_run_at", table_name="integrations")
    op.drop_index("ix_integrations_kind", table_name="integrations")
    op.drop_table("integrations")
