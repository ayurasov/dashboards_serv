"""Почтовая подписка на критичные статусы сквозного отчёта (этап 4, ADR-0012).

Раз в сутки планировщик проверяет подписчиков: если в области пользователя за сутки появились
подразделения в «критично» (или показатель стал «не заполнен»), отправляется одно письмо
со списком причин. SMTP — из окружения (`SMTP_HOST`, пусто — отправка выключена, подписки
не теряются). Письмо не отправляется дважды за день (`last_sent_day`), без SMTP — помечается
проверкой (`last_checked_at`), чтобы при настройке SMTP не прилетел поток старых писем.
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.db import utcnow
from ..models import StatusSubscription, User

log = logging.getLogger("app.subscription")


def get_subscription(db: Session, user_id: int) -> StatusSubscription:
    row = db.get(StatusSubscription, user_id)
    if row is None:
        row = StatusSubscription(user_id=user_id, enabled=False)
        db.add(row)
    return row


def set_subscription(db: Session, user_id: int, enabled: bool) -> StatusSubscription:
    row = get_subscription(db, user_id)
    row.enabled = enabled
    db.commit()
    return row


def _smtp_configured() -> bool:
    return bool(settings.smtp_host.strip())


def send_mail(to: str, subject: str, body: str) -> None:
    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = subject
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Date"] = formatdate(localtime=True)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


def _letter(db: Session, user: User) -> str | None:
    """Текст письма о критичных статусаx области пользователя; None — писать не о чем."""
    from . import org, reports

    try:
        snap = org.snapshot(db)
        st = reports.state(db)
        rep = st.report(db, st.current)
        viewer = reports.viewer_for(user, snap)
        view = rep.view(viewer.classes)
    except Exception:  # noqa: BLE001 — письмо не должно ломать такт планировщика
        log.exception("Подписка: не собрали сквозной отчёт для %s", user.username)
        return None
    lines: list[str] = []

    def walk(unit_id: int) -> None:
        status = view.status.get(unit_id)
        if status == "red":
            name = snap.units[unit_id].name
            lines.append(f"• {name} — критично")
            return  # вложенные не перечисляем: причина уже названа уровнем выше
        for child in snap.children.get(unit_id, ()):
            walk(child)

    for root in viewer.roots:
        walk(root)
    if not lines:
        return None
    head = (f"В области «{viewer_scope_label(viewer)}» появились подразделения в статусе «Критично».\n"
            f"Подробности — в сквозном отчёте: {settings.public_url or '(адрес задаётся PUBLIC_URL)'}\n")
    return head + "\n".join(lines[:20]) + (f"\n… и ещё {len(lines) - 20}" if len(lines) > 20 else "")


def viewer_scope_label(viewer) -> str:
    from .reports import ORG_SCOPE_LABELS

    return ORG_SCOPE_LABELS.get(viewer.scope, viewer.scope)


def run_daily(db: Session) -> dict:
    """Один прогон подписок (планировщик, раз в сутки). Возвращает счётчики для журнала."""
    sent = skipped = failed = subscribers = 0
    today = utcnow().date()
    if not _smtp_configured():
        for row in db.scalars(select(StatusSubscription).where(StatusSubscription.enabled.is_(True))):
            row.last_checked_at = utcnow()
            subscribers += 1
        db.commit()
        return {"sent": 0, "subscribers": subscribers, "skipped": 0, "failed": 0,
                "note": "SMTP не настроен — проверка без отправки"}
    users = {u.id: u for u in db.scalars(select(User).where(User.is_active.is_(True)))}
    for row in db.scalars(select(StatusSubscription).where(StatusSubscription.enabled.is_(True))):
        subscribers += 1
        user = users.get(row.user_id)
        if user is None or not user.email:
            skipped += 1
            continue
        if row.last_sent_day == today:
            skipped += 1
            continue
        try:
            body = _letter(db, user)
            if body:
                send_mail(user.email, "Дашборды: критичные статусы вашей области", body)
                row.last_sent_day = today
                sent += 1
        except Exception:  # noqa: BLE001 — одна неудача не останавливает остальных
            failed += 1
            log.exception("Подписка: письмо %s не отправлено", user.email)
        row.last_checked_at = utcnow()
        db.commit()
    return {"sent": sent, "subscribers": subscribers, "skipped": skipped, "failed": failed}
