# ─────────────────────────────────────────────
# Stage 1: build Vue.js frontend
# ─────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci --prefer-offline

COPY frontend/ ./
RUN npm run build
# Output: /app/frontend/dist


# ─────────────────────────────────────────────
# Stage 2: Python backend + serve built SPA
# ─────────────────────────────────────────────
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

# Copy compiled frontend into the place FastAPI expects (FRONTEND_DIST in main.py)
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist/

# Copy tp-report seed data so _seed_tp_rows() can find it under DATA_DIR
# If tp-report/seed_data.json doesn't exist yet, the COPY is a no-op warning; seed skips gracefully.
COPY tp-report/seed_data.json ./backend/app/data/tp_seed_data.json 2>/dev/null || true

# Persistent SQLite volume mount point
RUN mkdir -p /data

COPY backend/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONPATH=/app
ENV DATABASE_URL=sqlite:////data/hr_dashboard.db

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
