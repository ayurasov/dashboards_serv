"""Add tp_report_rows and tp_settings tables.

Revision ID: 0005_add_tp_tables
Revises: (previous head)
Create Date: 2026-08-25
"""
from alembic import op
import sqlalchemy as sa

revision = '0005_add_tp_tables'
down_revision = None   # set to the actual previous revision ID if known
branch_labels = None
depends_on = None


def upgrade() -> None:
    # tp_report_rows ----------------------------------------------------------
    op.create_table(
        'tp_report_rows',
        sa.Column('id',   sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('year', sa.Float(),  nullable=True),
        sa.Column('week', sa.Float(),  nullable=True),
        sa.Column('period', sa.String(50), nullable=True),
        sa.Column('total_in_work',  sa.Float(), nullable=True),
        sa.Column('avail_total',    sa.Float(), nullable=True),
        sa.Column('rushydro_hours',       sa.Float(), nullable=True),
        sa.Column('transneft_hours',      sa.Float(), nullable=True),
        sa.Column('roscosmos_hours',      sa.Float(), nullable=True),
        sa.Column('bryansk_hours',        sa.Float(), nullable=True),
        sa.Column('mchs_hours',           sa.Float(), nullable=True),
        sa.Column('internal_sales_hours', sa.Float(), nullable=True),
        sa.Column('new_received',          sa.Float(), nullable=True),
        sa.Column('renewed',               sa.Float(), nullable=True),
        sa.Column('ratio_solved_received', sa.Float(), nullable=True),
        sa.Column('altos_rusg_email',  sa.Float(), nullable=True),
        sa.Column('altos_rusg_tf',     sa.Float(), nullable=True),
        sa.Column('altos_other_email', sa.Float(), nullable=True),
        sa.Column('altos_other_tf',    sa.Float(), nullable=True),
        sa.Column('altoffice_rusg_email',  sa.Float(), nullable=True),
        sa.Column('altoffice_rusg_tf',     sa.Float(), nullable=True),
        sa.Column('altoffice_other_email', sa.Float(), nullable=True),
        sa.Column('altoffice_other_tf',    sa.Float(), nullable=True),
        sa.Column('projserver_taken',  sa.Float(), nullable=True),
        sa.Column('projserver_solved', sa.Float(), nullable=True),
        sa.Column('projserver_avail',  sa.Float(), nullable=True),
        sa.Column('total_solved_week', sa.Float(), nullable=True),
        sa.Column('altos_avg_time',    sa.Float(), nullable=True),
        sa.Column('altos_total',       sa.Float(), nullable=True),
        sa.Column('altos_1_2line',     sa.Float(), nullable=True),
        sa.Column('altos_3line',       sa.Float(), nullable=True),
        sa.Column('altoffice_avg_time',sa.Float(), nullable=True),
        sa.Column('altoffice_total',   sa.Float(), nullable=True),
        sa.Column('altoffice_1_2line', sa.Float(), nullable=True),
        sa.Column('altoffice_3line',   sa.Float(), nullable=True),
        sa.Column('altos_avail_total', sa.Float(), nullable=True),
        sa.Column('altos_avail_1_3',   sa.Float(), nullable=True),
        sa.Column('altos_avail_4_7',   sa.Float(), nullable=True),
        sa.Column('altos_avail_8_10',  sa.Float(), nullable=True),
        sa.Column('altoffice_avail_total', sa.Float(), nullable=True),
        sa.Column('altoffice_avail_1_3',   sa.Float(), nullable=True),
        sa.Column('altoffice_avail_4_7',   sa.Float(), nullable=True),
        sa.Column('altoffice_avail_8_10',  sa.Float(), nullable=True),
        sa.Column('extra',       sa.Text(),    nullable=True),
        sa.Column('created_at',  sa.DateTime(), nullable=True),
        sa.Column('updated_at',  sa.DateTime(), nullable=True),
    )

    # tp_settings -------------------------------------------------------------
    op.create_table(
        'tp_settings',
        sa.Column('key',   sa.String(80), primary_key=True),
        sa.Column('value', sa.Text(),     nullable=False, server_default='{}'),
    )


def downgrade() -> None:
    op.drop_table('tp_settings')
    op.drop_table('tp_report_rows')
