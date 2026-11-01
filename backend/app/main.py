"""Точка входа FastAPI: create_app() собирает приложение."""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import APP_NAME, __version__
from .api.routers import (
    access,
    auth,
    common,
    custom_dashboards,
    hr,
    inbound,
    inbox,
    integrations,
    naumen,
    org,
    partnerships,
    pdf,
    reports,
    system,
    tp,
    users,
)
from .core.config import settings
from .core.errors import install_error_handlers
from .core.logging import configure_logging
from .services.cache import accepts_gzip

log = logging.getLogger("app.http")

OPENAPI_TAGS = [
    {"name": "Вход и профиль"}, {"name": "Пользователи"}, {"name": "Подразделения"}, {"name": "Общее"},
    {"name": "Служба персонала"}, {"name": "Пользовательские дашборды"},
    {"name": "Техподдержка: недельный отчёт"}, {"name": "Техподдержка: заявки Naumen"},
    {"name": "Партнёрства"}, {"name": "Сквозные отчёты"}, {"name": "PDF-отчёты"}, {"name": "Входящие данные"},
    {"name": "Интеграции"}, {"name": "Приём по API"}, {"name": "Система"},
]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from anyio import to_thread

    to_thread.current_default_thread_limiter().total_tokens = (
        settings.threadpool_size or settings.db_pool_size + settings.db_max_overflow + 8)
    if settings.migrate_on_start:
        from .cli import cmd_migrate

        cmd_migrate(None)
    log.info("%s %s запущен (%s)", APP_NAME, __version__, settings.app_env)
    yield


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title=f"{APP_NAME} — API",
        version=__version__,
        description="API дашбордов служб компании: служба персонала, техническая поддержка, "
                    "технологические партнёрства. Аутентификация — сессионная cookie и заголовок X-CSRF-Token.",
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    install_error_handlers(app)
    app.add_middleware(GZipMiddleware, minimum_size=2048)
    if settings.cors_list:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True,
                           allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        accepts_gzip.set("gzip" in request.headers.get("accept-encoding", ""))
        started = time.perf_counter()
        response = await call_next(request)
        duration = round((time.perf_counter() - started) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
            if request.url.path != "/api/health":
                log.info("%s %s → %s (%s мс)", request.method, request.url.path, response.status_code, duration,
                         extra={"request_id": request_id, "method": request.method, "path": request.url.path,
                                "status": response.status_code, "duration_ms": duration})
        return response

    for module in (auth, users, access, org, common, hr, custom_dashboards, tp, naumen, partnerships, reports, pdf,
                   inbox, integrations, inbound, system):
        app.include_router(module.router)
    app.include_router(org.departments_router)

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    async def api_not_found(path: str):
        body = {"detail": "Ресурс API не найден", "code": "not_found"}
        if path.startswith("inbound/"):
            body.update(error="not_found", message=body["detail"])
        return JSONResponse(body, status_code=404)

    _mount_frontend(app, settings.frontend_dist)
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Собранный интерфейс (frontend/dist) раздаётся тем же сервером; маршруты SPA — через index.html."""
    index = dist / "index.html"
    if not index.exists():
        return
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()
