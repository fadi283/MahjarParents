"""Gunicorn configuration tuned for 512 MB free-tier PaaS containers."""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
worker_class = "gthread"
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
threads = int(os.environ.get("GUNICORN_THREADS", "8"))
backlog = int(os.environ.get("GUNICORN_BACKLOG", "2048"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
