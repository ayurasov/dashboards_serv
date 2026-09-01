# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: build Vue.js frontend
# ─────────────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json ./
RUN npm cache clean --force \
    && npm install --no-package-lock --prefer-online --cache /tmp/npm-cache --no-audit --no-fund \
    && npm cache clean --force

COPY frontend/ ./
RUN npm run build


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Python backend + serve built SPA
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS backend

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist/
COPY tp-report/seed_data.json ./backend/app/data/tp_seed_data.json

RUN mkdir -p /data

# Copy the script as data, then invoke it through the interpreter. This avoids
# Docker failing before process start when executable metadata or a shebang is
# not preserved by the checkout filesystem.
COPY backend/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh \
    && chmod 755 /entrypoint.sh

ENV PYTHONPATH=/app
ENV DATABASE_URL=sqlite:////data/hr_dashboard.db

EXPOSE 8000

ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]
