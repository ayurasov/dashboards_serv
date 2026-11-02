# syntax=docker/dockerfile:1
# Дашборды компании: интерфейс (Vue) собирается отдельной стадией и раздаётся сервером (FastAPI).

# ---------- интерфейс ----------
FROM node:22-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Руководства и история версий встраиваются в приложение
COPY docs/ /build/docs/
RUN npm run build

# ---------- сервер ----------
FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    FRONTEND_DIST=/app/frontend/dist \
    MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --home /app app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend/ backend/
COPY --from=frontend /build/frontend/dist frontend/dist/
RUN sed -i 's/\r$//' backend/docker-entrypoint.sh && chmod 755 backend/docker-entrypoint.sh \
    && mkdir -p /data/inbox && chown -R app:app /data /app
USER app
# Рабочий каталог — сервер: «docker compose exec app python -m app.cli …» работает без -w
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
ENTRYPOINT ["/bin/sh", "/app/backend/docker-entrypoint.sh"]
