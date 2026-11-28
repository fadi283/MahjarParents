import io
import json
import os
from pathlib import Path
import runpy
import sqlite3
import tomllib

import cv2
import numpy as np
import pytest
from werkzeug.security import generate_password_hash

import app as backend_app
import cms_store
import media_pipeline
import platform_security

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = PROJECT_ROOT / "backend"



@pytest.mark.unit
class TestSQLiteCMSStore:
    """Unit tests for lightweight SQLite CMS persistence and JSON migration."""

    def test_sqlite_store_creates_wal_schema_seeds_once_and_persists_crud(self, tmp_path):
        db_path = tmp_path / "cms_data.sqlite3"
        store = cms_store.SQLiteCMSStore(
            backend_app.DEFAULT_COMMITTEE_MEMBERS,
            backend_app.DEFAULT_POSTS,
            cms_store.DEFAULT_GOOGLE_FORMS,
            db_path=db_path,
        )

        with sqlite3.connect(db_path) as conn:
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(journal_mode).lower() == "wal"

        info = store.storage_info()
        assert info["backend"] == "sqlite"
        assert info["persisted"] is True
        assert info["sizeBytes"] > 0
        assert "counts" in info
        assert info["counts"]["committee"] == len(backend_app.DEFAULT_COMMITTEE_MEMBERS)
        assert info["counts"]["posts"] == len(backend_app.DEFAULT_POSTS)
        assert info["counts"]["forms"] == len(cms_store.DEFAULT_GOOGLE_FORMS)
        assert "path" not in info

        # Committee CRUD
        created_member = store.create_committee_member({
            "fullName": "عضو SQLite جديد",
            "role": "عضو لجنة",
            "responsibilitySummary": "تنسيق الفعاليات.",
            "email": "sqlite@example.com",
            "phone": "0501234567",
            "avatarUrl": "/api/media/images/0123456789abcdef.webp",
            "displayOrder": 20,
        })
        member_id = created_member["id"]
        assert store.get_committee_member(member_id)["fullName"] == "عضو SQLite جديد"
        updated_member = store.update_committee_member(member_id, {"role": "منسق رئيسي"})
        assert updated_member["role"] == "منسق رئيسي"

        # Posts + cascade mediaLinks CRUD
        created_post = store.create_post(
            {
                "title": "منشور SQLite تجريبي",
                "summary": "اختبار الحفظ الدائم في SQLite.",
                "category": "updates",
                "publishedAt": "2026-11-25T10:00:00Z",
                "eventDate": "",
                "imageUrl": "/api/media/images/0123456789abcdef.webp",
            },
            media_links=[
                {
                    "mediaType": "video",
                    "provider": "youtube",
                    "canonicalUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "embedUrl": "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
                    "originalUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "hostedExternally": True,
                    "title": "فيديو تعريفي",
                }
            ],
        )
        post_id = created_post["id"]
        assert len(created_post["mediaLinks"]) == 1

        standalone_link = store.create_media_link({
            "postId": None,
            "mediaType": "audio",
            "provider": "soundcloud",
            "canonicalUrl": "https://soundcloud.com/school/clip",
            "embedUrl": "https://w.soundcloud.com/player/?url=https%3A%2F%2Fsoundcloud.com%2Fschool%2Fclip",
            "originalUrl": "https://soundcloud.com/school/clip",
            "hostedExternally": True,
            "title": "ملف صوتي",
        })
        assert store.get_media_link(standalone_link["id"])["title"] == "ملف صوتي"

        # Forms CRUD + ordering
        created_form = store.create_form({
            "formType": "feedback",
            "title": "استمارة SQLite",
            "description": "وصف",
            "canonicalUrl": "https://docs.google.com/forms/d/e/1FAIpQLScSqliteTest01/viewform",
            "embedUrl": "https://docs.google.com/forms/d/e/1FAIpQLScSqliteTest01/viewform?embedded=true",
            "provider": "google_forms",
            "formId": "1FAIpQLScSqliteTest01",
            "active": True,
            "displayOrder": 1,
        })
        assert store.get_form(created_form["id"])["title"] == "استمارة SQLite"

        # Delete latest member and post; verify monotonic IDs and cascade on restart
        assert store.delete_committee_member(member_id) is True
        assert store.delete_committee_member(member_id) is False
        assert store.delete_post(post_id) is True
        assert store.list_media_links(post_id=post_id) == []

        reopened = cms_store.SQLiteCMSStore(
            backend_app.DEFAULT_COMMITTEE_MEMBERS,
            backend_app.DEFAULT_POSTS,
            cms_store.DEFAULT_GOOGLE_FORMS,
            db_path=db_path,
        )
        next_member = reopened.create_committee_member({
            "fullName": "عضو بعد إعادة التشغيل",
            "role": "عضو",
            "responsibilitySummary": "",
            "email": "",
            "phone": "",
            "avatarUrl": "",
            "displayOrder": None,
        })
        assert next_member["id"] > member_id
        assert reopened.get_post(post_id) is None
        assert reopened.get_form(created_form["id"])["title"] == "استمارة SQLite"

        # Deleting every form must NOT re-seed defaults on reopen
        for form in reopened.list_forms():
            assert reopened.delete_form(form["id"]) is True
        reopened_empty = cms_store.SQLiteCMSStore(
            backend_app.DEFAULT_COMMITTEE_MEMBERS,
            backend_app.DEFAULT_POSTS,
            cms_store.DEFAULT_GOOGLE_FORMS,
            db_path=db_path,
        )
        assert reopened_empty.list_forms() == []

    def test_create_cms_store_factory_and_json_storage_info(self, tmp_path):
        json_path = tmp_path / "store.json"
        json_store = cms_store.create_cms_store(
            backend_app.DEFAULT_COMMITTEE_MEMBERS,
            backend_app.DEFAULT_POSTS,
            cms_store.DEFAULT_GOOGLE_FORMS,
            data_file=json_path,
            storage_backend="auto",
        )
        assert isinstance(json_store, cms_store.CMSStore)
        json_info = json_store.storage_info()
        assert json_info["backend"] == "json"
        assert json_info["persisted"] is True
        assert "counts" in json_info
        assert "path" not in json_info

        sqlite_file = tmp_path / "auto.sqlite3"
        sqlite_store = cms_store.create_cms_store(
            backend_app.DEFAULT_COMMITTEE_MEMBERS,
            backend_app.DEFAULT_POSTS,
            cms_store.DEFAULT_GOOGLE_FORMS,
            data_file=sqlite_file,
            storage_backend="auto",
        )
        assert isinstance(sqlite_store, cms_store.SQLiteCMSStore)

        mem_store = cms_store.create_cms_store(
            backend_app.DEFAULT_COMMITTEE_MEMBERS,
            backend_app.DEFAULT_POSTS,
            cms_store.DEFAULT_GOOGLE_FORMS,
            storage_backend="sqlite",
            database_url="sqlite:///:memory:",
        )
        assert isinstance(mem_store, cms_store.SQLiteCMSStore)
        assert mem_store.storage_info()["persisted"] is False

        url_path = tmp_path / "from_url.db"
        url_store = cms_store.create_cms_store(
            backend_app.DEFAULT_COMMITTEE_MEMBERS,
            backend_app.DEFAULT_POSTS,
            cms_store.DEFAULT_GOOGLE_FORMS,
            database_url=f"sqlite:///{url_path}",
        )
        assert isinstance(url_store, cms_store.SQLiteCMSStore)
        assert url_path.is_file()

        with pytest.raises(ValueError):
            cms_store.create_cms_store([], [], [], storage_backend="postgres")

        with pytest.raises(ValueError):
            cms_store.create_cms_store([], [], [], storage_backend="mysql")

        with pytest.raises(ValueError):
            cms_store.create_cms_store([], [], [], database_url="mysql://user:pass@host/db")

        with pytest.raises(ValueError):
            cms_store.create_cms_store(
                [], [], [], storage_backend="json", database_url="postgresql://user:pass@host/db"
            )

        with pytest.raises(ValueError):
            cms_store.create_cms_store(
                [], [], [], storage_backend="sqlite", database_url="postgresql://user:pass@host/db"
            )

    def test_migrate_json_to_sqlite_preserves_records_and_sequences(self, tmp_path):
        json_path = tmp_path / "legacy.json"
        sqlite_path = tmp_path / "migrated.sqlite3"

        legacy = cms_store.CMSStore(
            backend_app.DEFAULT_COMMITTEE_MEMBERS,
            backend_app.DEFAULT_POSTS,
            cms_store.DEFAULT_GOOGLE_FORMS,
            data_file=json_path,
        )
        custom_post = legacy.create_post(
            {
                "title": "منشور مُرحّل",
                "summary": "محتوى من JSON إلى SQLite.",
                "category": "general",
                "publishedAt": "2026-11-25T12:00:00Z",
                "eventDate": "",
                "imageUrl": "",
            },
            media_links=[
                {
                    "mediaType": "video",
                    "provider": "vimeo",
                    "canonicalUrl": "https://vimeo.com/12345678",
                    "embedUrl": "https://player.vimeo.com/video/12345678",
                    "originalUrl": "https://vimeo.com/12345678",
                    "hostedExternally": True,
                    "title": "Vimeo clip",
                }
            ],
        )

        summary = cms_store.migrate_json_to_sqlite(json_path, sqlite_path)
        assert summary["posts"] == len(legacy.list_posts())

        migrated = cms_store.SQLiteCMSStore(
            backend_app.DEFAULT_COMMITTEE_MEMBERS,
            backend_app.DEFAULT_POSTS,
            cms_store.DEFAULT_GOOGLE_FORMS,
            db_path=sqlite_path,
        )
        fetched = migrated.get_post(custom_post["id"])
        assert fetched is not None
        assert fetched["title"] == "منشور مُرحّل"
        assert len(fetched["mediaLinks"]) == 1
        next_post = migrated.create_post({
            "title": "منشور بعد الترحيل",
            "summary": "تسلسل سليم",
            "category": "updates",
            "publishedAt": "2026-11-25T13:00:00Z",
            "eventDate": "",
            "imageUrl": "",
        })
        assert next_post["id"] > custom_post["id"]



@pytest.mark.unit
@pytest.mark.smoke
class TestWSGIAndDeploymentArtifacts:
    """Tests verifying free-tier WSGI entrypoint and PaaS/CI-CD configuration manifests."""

    def test_wsgi_and_gunicorn_config_and_requirements(self):
        import sys

        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))
        import wsgi

        assert callable(wsgi.app)
        assert callable(wsgi.application)

        gunicorn_ns = runpy.run_path(str(BACKEND_DIR / "gunicorn.conf.py"))
        assert gunicorn_ns["worker_class"] == "gthread"
        assert gunicorn_ns["workers"] == 1
        assert gunicorn_ns["threads"] >= 2
        assert ":5000" in gunicorn_ns["bind"] or gunicorn_ns["bind"].startswith("0.0.0.0:")

        req_lines = [
            line.strip().lower()
            for line in (BACKEND_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        assert any(line.startswith("gunicorn==") for line in req_lines)
        assert any(line.startswith("opencv-python-headless==") for line in req_lines)
        assert not any(line.startswith("opencv-python==") for line in req_lines)

    def test_free_tier_deployment_manifests_and_ci_workflow(self):
        vercel = json.loads((PROJECT_ROOT / "vercel.json").read_text(encoding="utf-8"))
        assert "frontend" in vercel["buildCommand"]
        assert vercel["outputDirectory"] == "frontend/dist"
        assert any(r.get("destination") == "/index.html" for r in vercel.get("rewrites", []))
        assert any(
            h.get("source") == "/assets/(.*)"
            for h in vercel.get("headers", [])
        )

        netlify = tomllib.loads((PROJECT_ROOT / "netlify.toml").read_text(encoding="utf-8"))
        assert netlify["build"]["base"] == "frontend"
        assert netlify["build"]["publish"] == "dist"
        assert any(
            r.get("from") == "/*" and r.get("to") == "/index.html" and r.get("status") == 200
            for r in netlify.get("redirects", [])
        )

        render_text = (PROJECT_ROOT / "render.yaml").read_text(encoding="utf-8")
        assert "plan: free" in render_text
        assert "gunicorn" in render_text
        assert "/api/health" in render_text
        assert "MAHJAR_STORAGE_BACKEND" in render_text
        assert "frontend" in render_text

        procfile_text = (PROJECT_ROOT / "Procfile").read_text(encoding="utf-8")
        assert "web:" in procfile_text
        assert "gunicorn" in procfile_text
        assert "wsgi:app" in procfile_text

        dockerfile_text = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "node:22-alpine" in dockerfile_text
        assert "python:3.12-slim" in dockerfile_text
        assert "MAHJAR_SERVE_FRONTEND=true" in dockerfile_text
        assert "USER " in dockerfile_text
        assert "HEALTHCHECK" in dockerfile_text

        dockerignore_text = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
        for ignored in (".env", "venv", "node_modules", "backend/uploads"):
            assert ignored in dockerignore_text

        workflow_text = (PROJECT_ROOT / ".github" / "workflows" / "ci-cd.yml").read_text(encoding="utf-8")
        assert "pytest" in workflow_text
        assert "npm test" in workflow_text
        assert "npm run build" in workflow_text
        assert "build:verify" in workflow_text

        env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        for key in (
            "MAHJAR_DATA_DIR",
            "MAHJAR_STORAGE_BACKEND",
            "MAHJAR_MAX_MEDIA_STORAGE_BYTES",
            "MAHJAR_SERVE_FRONTEND",
        ):
            assert key in env_example

        fe_env_example = (PROJECT_ROOT / "frontend" / ".env.example").read_text(encoding="utf-8")
        assert "VITE_API_BASE_URL" in fe_env_example
        assert (PROJECT_ROOT / "docs" / "deployment_free_tier.md").is_file()

