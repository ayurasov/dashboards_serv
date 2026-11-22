"""Почтовая подписка на критичные статусы (версия 0.6.0, этап 4, ADR-0012).

- status_subscriptions — вкл/выкл на пользователя (по умолчанию выключено), отметки
  последней проверки и последнего отправленного дня — чтобы не слать письмо дважды.

Отправка — планировщиком раз в сутки (SMTP-настройки в окружении); письмо получают
подписчики, в области которых за сутки появились «критичные» подразделения сквозного отчёта.

Revision ID: 0020_status_subscription
Revises: 0019_project_office_service
"""
import sqlalchemy as sa
from alembic import op

revision = "0020_status_subscription"
down_revision = "0019_project_office_service"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "status_subscriptions",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("last_sent_day", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("status_subscriptions")
