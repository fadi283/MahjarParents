"""WSGI entrypoint for free-tier production servers (Gunicorn / Waitress)."""

from pathlib import Path
import sys

_BACKEND_DIR = str(Path(__file__).resolve().parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app import create_app

app = create_app()
application = app
