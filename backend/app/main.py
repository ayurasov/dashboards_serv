"""FastAPI application entry point."""
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .config import settings
from .database import Base, engine, ensure_added_columns
from .seed import seed_all
from .routers import (
    auth, users, hr, traffic_light, dashboards, dashboard_prefs, audit, pdf,
    partnerships, modules, palette, tp,
)

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_added_columns()
    seed_all()
    yield

app = FastAPI(
    title="HR Dashboard API — АЛМИ Партнер",
    version="1.0.0",
    description="API службы персонала с ролевой моделью, аналитикой и экспортом",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.cors_origins == "*" else settings.cors_list,
    allow_credentials=settings.cors_origins != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(hr.router)
app.include_router(traffic_light.router)
app.include_router(dashboards.router)
app.include_router(dashboard_prefs.router)
app.include_router(audit.router)
app.include_router(pdf.router)
app.include_router(partnerships.router)
app.include_router(modules.router)
app.include_router(modules.services_router)
app.include_router(palette.router)
app.include_router(tp.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "hr-dashboard-api"}


# Serve frontend static files (SPA fallback) — MUST be last
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        file_path = FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
