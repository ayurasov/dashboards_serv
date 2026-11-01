"""Ревизии данных служб — для согласованного сброса кэша ответов во всех процессах.

Revision ID: 0013_data_revisions
Revises: 0012_v0_1_0_schema
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_data_revisions"
down_revision = "0012_v0_1_0_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_revisions",
        sa.Column("service_key", sa.String(40), nullable=False),
        sa.Column("revision", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("service_key", name="pk_data_revisions"),
        sa.ForeignKeyConstraint(["service_key"], ["services.key"], name="fk_data_revisions_service_key_services",
                                ondelete="CASCADE", onupdate="CASCADE"),
    )
    op.execute("INSERT INTO data_revisions (service_key, revision, updated_at) "
               "SELECT key, 0, CURRENT_TIMESTAMP FROM services")


def downgrade() -> None:
    op.drop_table("data_revisions")
