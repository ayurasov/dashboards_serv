"""Состояние сервиса, версия, сведения о системе."""
from __future__ import annotations

import platform

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ... import APP_NAME, __version__
from ...core.config import settings
from ...core.db import engine, get_db
from ...core.migrate import check_schema_is_current
from ...models import AuditEntry, DataImport, HrMonth, NaumenTicket, Partnership, TpWeeklyReport, User, UserSession
from ..deps import require_admin

router = APIRouter(prefix="/api", tags=["Система"])


@router.get("/health", summary="Проверка работоспособности (для балансировщика и Docker)")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            ok, current, head = check_schema_is_current(conn)
    except Exception as exc:  # pragma: no cover - база недоступна
        return JSONResponse({"status": "error", "version": __version__, "database": "unavailable",
                             "detail": exc.__class__.__name__}, status_code=503)
    status = "ok" if ok else "degraded"
    return JSONResponse({"status": status, "version": __version__, "database": "ok",
                         "schema": {"current": current, "head": head}},
                        status_code=200 if ok else 503)


@router.get("/version", summary="Версия приложения")
def version():
    return {"name": APP_NAME, "version": __version__}


@router.get("/system/info", summary="Сведения о системе (администратор)")
def system_info(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    with engine.connect() as conn:
        ok, current, head = check_schema_is_current(conn)

    def count(model) -> int:
        return db.scalar(select(func.count()).select_from(model)) or 0

    last_import = db.scalar(select(DataImport).order_by(DataImport.created_at.desc()).limit(1))
    return {
        "name": APP_NAME,
        "version": __version__,
        "environment": settings.app_env,
        "python": platform.python_version(),
        "database": {
            "dialect": engine.dialect.name,
            "server_version": ".".join(map(str, engine.dialect.server_version_info or ())),
            "schema_current": current,
            "schema_head": head,
            "schema_ok": ok,
        },
        "counts": {
            "users": count(User),
            "active_sessions": count(UserSession),
            "hr_months": count(HrMonth),
            "tp_weeks": count(TpWeeklyReport),
            "naumen_tickets": count(NaumenTicket),
            "partnerships": count(Partnership),
            "audit_entries": count(AuditEntry),
        },
        "last_import": None if last_import is None else {
            "dataset": last_import.dataset, "filename": last_import.filename,
            "created_at": last_import.created_at, "username": last_import.username,
        },
        "settings": {
            "demo_data": settings.demo_data,
            "session_lifetime_hours": settings.session_lifetime_hours,
            "session_idle_minutes": settings.session_idle_minutes,
            "password_min_length": settings.password_min_length,
            "max_upload_mb": settings.max_upload_mb,
        },
    }
