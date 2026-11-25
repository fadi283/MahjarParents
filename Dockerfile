# Stage 1: Build static React SPA bundle (zero raw video/audio assets)
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build && npm run build:verify

# Stage 2: Lightweight Python + OpenCV-headless + Gunicorn runtime
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000 \
    MAHJAR_ENV=production \
    MAHJAR_STORAGE_BACKEND=sqlite \
    MAHJAR_DATA_DIR=/var/data \
    MAHJAR_MAX_MEDIA_STORAGE_BYTES=52428800 \
    MAHJAR_SERVE_FRONTEND=true \
    MAHJAR_FRONTEND_DIST_DIR=/app/frontend/dist

WORKDIR /app

# Runtime libs required by opencv-python-headless on Debian slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

RUN useradd --create-home --shell /bin/sh appuser \
    && mkdir -p /var/data/uploads/images \
    && chown -R appuser:appuser /app /var/data

USER appuser
VOLUME ["/var/data"]
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os, urllib.request; port=os.environ.get('PORT', '5000'); urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=3)" || exit 1

CMD ["gunicorn", "--chdir", "backend", "-c", "backend/gunicorn.conf.py", "wsgi:app"]
