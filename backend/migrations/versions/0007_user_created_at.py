"""Add columns present in the User ORM model but missing from the legacy schema.

Revision ID: 0007_user_created_at
Revises:     0006_metric_definition_id
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_user_created_at"
down_revision = "0006_metric_definition_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "created_at" not in columns:
        op.add_column(
            "users",
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=True,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "created_at" in columns:
        op.drop_column("users", "created_at")
