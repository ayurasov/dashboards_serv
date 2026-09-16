"""Create naumen_tickets table for Naumen SD analytics.

Revision ID: 0011_naumen_tickets
Revises:     0010_align_remaining_orm_tables
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_naumen_tickets"
down_revision = "0010_align_remaining_orm_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "naumen_tickets" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "naumen_tickets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("number", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(50), nullable=True),
        sa.Column("registered_at", sa.DateTime(), nullable=True),
        sa.Column("solved_at", sa.DateTime(), nullable=True),
        sa.Column("deadline_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(100), nullable=True),
        sa.Column("org", sa.String(300), nullable=True),
        sa.Column("responsible", sa.String(300), nullable=True),
        sa.Column("team", sa.String(200), nullable=True),
        sa.Column("first_line", sa.String(300), nullable=True),
        sa.Column("channel", sa.String(100), nullable=True),
        sa.Column("overdue", sa.Boolean(), nullable=False, default=False),
        sa.Column("reopened", sa.Boolean(), nullable=False, default=False),
        sa.Column("processing_hours", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_naumen_tickets_number", "naumen_tickets", ["number"])
    op.create_index("ix_naumen_tickets_registered_at", "naumen_tickets", ["registered_at"])
    op.create_index("ix_naumen_tickets_solved_at", "naumen_tickets", ["solved_at"])
    op.create_index("ix_naumen_tickets_org", "naumen_tickets", ["org"])


def downgrade() -> None:
    bind = op.get_bind()
    if "naumen_tickets" in sa.inspect(bind).get_table_names():
        op.drop_table("naumen_tickets")
