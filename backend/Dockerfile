# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: build Vue.js frontend
# ─────────────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json ./
# package-lock.json currently contains invalid integrity metadata for Chart.js.
# Install directly from the registry and disable npm's local cache so a corrupted
# tarball cannot be reused across Docker builds.
RUN npm cache clean --force \
    && npm install --no-package-lock --prefer-online --cache /tmp/npm-cache --no-audit --no-fund \
    && npm cache clean --force

COPY frontend/ ./
RUN npm run build
# Output: /build/frontend/dist


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Python backend + serve built SPA
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS backend

# System deps: curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application source
COPY backend/ ./backend/

# Built frontend dist — FastAPI main.py resolves:
#   FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"
# which under /app equals /app/frontend/dist
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist/

# TP seed data: seed.py looks for DATA_DIR/tp_seed_data.json as Docker fallback.
# The file must exist in the repo at tp-report/seed_data.json.
# If it is absent, remove this line — seed.py skips TP rows gracefully.
COPY tp-report/seed_data.json ./backend/app/data/tp_seed_data.json

# Persistent SQLite volume mount point
RUN mkdir -p /data

COPY backend/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONPATH=/app
ENV DATABASE_URL=sqlite:////data/hr_dashboard.db

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
