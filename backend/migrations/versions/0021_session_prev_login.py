"""Лента «что изменилось с прошлого входа» (версия 0.6.0, этап 4).

- user_sessions.prev_login_at — каким был последний вход до этой сессии: в момент входа
  фиксируется прошлый last_login_at пользователя, лента читает его; справочники и входы
  в ленту не попадают (семантика — план 0.5.0).

Revision ID: 0021_session_prev_login
Revises: 0020_status_subscription
"""
import sqlalchemy as sa
from alembic import op

revision = "0021_session_prev_login"
down_revision = "0020_status_subscription"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_sessions", sa.Column("prev_login_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_sessions", "prev_login_at")
