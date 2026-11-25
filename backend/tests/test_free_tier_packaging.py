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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"


def _make_png_bytes(width: int = 32, height: int = 32, color=(20, 90, 160)) -> bytes:
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :] = color
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


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
            cms_store.create_cms_store([], [], [], database_url="postgresql://user:pass@host/db")

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


@pytest.mark.api
class TestUnifiedDataDirAndMediaQuota:
    """Integration tests for free-tier persistent disk layout, SQLite restart persistence, and image quota."""

    def test_data_dir_persists_sqlite_cms_and_opencv_assets_across_restarts(self, monkeypatch, tmp_path):
        data_dir = tmp_path / "persistent_disk"
        pw = "MahjarFreeTier#2026"
        monkeypatch.setenv("MAHJAR_ENV", "production")
        monkeypatch.setenv("MAHJAR_SECRET_KEY", "x" * 48)
        monkeypatch.setenv("MAHJAR_ADMIN_USERNAME", "admin")
        monkeypatch.setenv("MAHJAR_ADMIN_PASSWORD_HASH", generate_password_hash(pw))
        monkeypatch.setenv("MAHJAR_CORS_ALLOWED_ORIGINS", "https://mahjar-parents.vercel.app")
        monkeypatch.setenv("MAHJAR_DATA_DIR", str(data_dir))
        monkeypatch.setenv("MAHJAR_STORAGE_BACKEND", "sqlite")

        app1 = backend_app.create_app()
        assert app1.extensions["cms_store"].storage_info()["backend"] == "sqlite"
        assert (data_dir / "cms_data.sqlite3").is_file()

        with app1.test_client() as c1:
            login = c1.post(
                "/api/admin/auth/login",
                headers={"X-Forwarded-Proto": "https"},
                json={"username": "admin", "password": pw},
            )
            assert login.status_code == 200
            headers = {
                "X-Forwarded-Proto": "https",
                "Authorization": f"Bearer {login.get_json()['token']}",
            }

            upload = c1.post(
                "/api/media/images",
                headers=headers,
                data={"file": (io.BytesIO(_make_png_bytes(64, 64, (40, 120, 200))), "flyer.png", "image/png")},
                content_type="multipart/form-data",
            )
            assert upload.status_code == 201
            image_url = upload.get_json()["url"]
            image_filename = upload.get_json()["filename"]
            assert (data_dir / "uploads" / "images" / image_filename).is_file()

            created_post = c1.post(
                "/api/admin/posts",
                headers=headers,
                json={
                    "title": "إعلان محفوظ على القرص",
                    "summary": "تم الحفظ في SQLite مع صورة WebP محسّنة.",
                    "category": "updates",
                    "imageUrl": image_url,
                },
            )
            assert created_post.status_code == 201

            # Raw A/V upload is rejected and writes nothing
            raw_mp4 = c1.post(
                "/api/media/images",
                headers=headers,
                data={"file": (io.BytesIO(b"\x00\x00\x00\x18ftypmp42"), "clip.mp4", "video/mp4")},
                content_type="multipart/form-data",
            )
            assert raw_mp4.status_code == 415
            assert raw_mp4.get_json()["code"] == "RAW_AV_NOT_ALLOWED"

        backend_app.clear_posts_cache()
        app2 = backend_app.create_app()
        with app2.test_client() as c2:
            posts_resp = c2.get("/api/posts", headers={"X-Forwarded-Proto": "https"})
            assert posts_resp.status_code == 200
            titles = [p["title"] for p in posts_resp.get_json()]
            assert "إعلان محفوظ على القرص" in titles

            img_resp = c2.get(image_url, headers={"X-Forwarded-Proto": "https"})
            assert img_resp.status_code == 200
            assert img_resp.mimetype == "image/webp"

    def test_media_storage_inspection_and_quota_enforcement(self, tmp_path):
        first_bytes = _make_png_bytes(120, 120, (10, 30, 50))
        second_bytes = _make_png_bytes(120, 120, (210, 180, 90))

        first_opt = media_pipeline.optimize_image(first_bytes, filename="one.png", content_type="image/png")
        asset_size = first_opt["optimizedBytes"]

        upload_dir = tmp_path / "quota_uploads"
        quota_app = backend_app.create_app({
            "TESTING": True,
            "MEDIA_UPLOAD_DIR": str(upload_dir),
            "CMS_DATA_FILE": str(tmp_path / "quota.sqlite3"),
            "STORAGE_BACKEND": "sqlite",
            "MAX_MEDIA_STORAGE_BYTES": asset_size + 100,
        })

        with quota_app.test_client() as c:
            import io

            r1 = c.post(
                "/api/media/images",
                data={"file": (io.BytesIO(first_bytes), "one.png", "image/png")},
                content_type="multipart/form-data",
            )
            assert r1.status_code == 201

            # Idempotent re-upload of identical image succeeds even near quota
            r1_dup = c.post(
                "/api/media/images",
                data={"file": (io.BytesIO(first_bytes), "one.png", "image/png")},
                content_type="multipart/form-data",
            )
            assert r1_dup.status_code == 201

            # Distinct image exceeds free-tier quota -> 507 STORAGE_QUOTA_EXCEEDED
            r2 = c.post(
                "/api/media/images",
                data={"file": (io.BytesIO(second_bytes), "two.png", "image/png")},
                content_type="multipart/form-data",
            )
            assert r2.status_code == 507
            assert r2.get_json()["code"] == "STORAGE_QUOTA_EXCEEDED"

        # Stray raw A/V file detection in inspect_media_storage
        (upload_dir / "stray.mp4").write_bytes(b"fake")
        stats = media_pipeline.inspect_media_storage(upload_dir)
        assert stats["assetCount"] == 1
        assert stats["usedBytes"] == asset_size
        assert stats["disallowedFiles"] == 1


@pytest.mark.api
class TestReadinessAndFrontendBundleServing:
    """Integration tests for /api/ready diagnostics and optional Flask SPA dist serving."""

    def test_health_unchanged_and_ready_reports_storage_and_media_budget(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MAHJAR_ENV", "production")
        monkeypatch.setenv("MAHJAR_SECRET_KEY", "z" * 48)
        monkeypatch.setenv("MAHJAR_ADMIN_USERNAME", "admin")
        monkeypatch.setenv("MAHJAR_ADMIN_PASSWORD_HASH", generate_password_hash("StrongReady!2026"))
        monkeypatch.setenv("MAHJAR_CORS_ALLOWED_ORIGINS", "https://mahjar.netlify.app")
        monkeypatch.setenv("MAHJAR_DATA_DIR", str(tmp_path / "ready_data"))
        monkeypatch.setenv("MAHJAR_STORAGE_BACKEND", "sqlite")

        prod_app = backend_app.create_app()
        assert "/api/ready" in platform_security.DEFAULT_HTTPS_EXEMPT_PATHS

        with prod_app.test_client() as c:
            health = c.get("/api/health")
            assert health.status_code == 200
            assert health.get_json() == {
                "status": "ok",
                "service": "MahjarParents Backend API",
            }

            ready = c.get("/api/ready")
            assert ready.status_code == 200
            body = ready.get_json()
            assert body["status"] == "ready"
            assert body["storage"]["backend"] == "sqlite"
            assert body["storage"]["persisted"] is True
            assert body["media"]["rawAvStorageAllowed"] is False
            assert body["media"]["maxStorageBytes"] > 0
            assert body["frontend"]["servedByFlask"] is False
            assert "no-store" in ready.headers.get("Cache-Control", "")
            raw_text = ready.get_data(as_text=True)
            assert str(tmp_path) not in raw_text
            assert "z" * 48 not in raw_text

    def test_flask_serves_built_react_spa_with_cache_and_csp_while_preserving_api(self, tmp_path):
        dist_dir = tmp_path / "dist"
        assets_dir = dist_dir / "assets"
        assets_dir.mkdir(parents=True)
        (dist_dir / "index.html").write_text(
            '<!doctype html><html lang="ar" dir="rtl"><body><div id="root"></div></body></html>',
            encoding="utf-8",
        )
        (dist_dir / "logo.jpg").write_bytes(b"\xff\xd8\xff\xe0logo")
        (assets_dir / "app-abc123.js").write_text("console.log('mahjar');", encoding="utf-8")
        (dist_dir / "illegal.mp4").write_bytes(b"video")

        spa_app = backend_app.create_app({
            "TESTING": True,
            "CMS_DATA_FILE": str(tmp_path / "spa.sqlite3"),
            "STORAGE_BACKEND": "sqlite",
            "MEDIA_UPLOAD_DIR": str(tmp_path / "spa_uploads"),
            "SERVE_FRONTEND_DIST": True,
            "FRONTEND_DIST_DIR": str(dist_dir),
        })

        with spa_app.test_client() as c:
            root_resp = c.get("/")
            assert root_resp.status_code == 200
            assert 'dir="rtl"' in root_resp.get_data(as_text=True)
            assert "no-cache" in root_resp.headers.get("Cache-Control", "")
            root_csp = root_resp.headers.get("Content-Security-Policy", "")
            assert "https://docs.google.com" in root_csp
            assert "https://www.youtube-nocookie.com" in root_csp
            assert "https://www.instagram.com" in root_csp
            assert "https://www.facebook.com" in root_csp
            assert "https://www.tiktok.com" in root_csp
            assert "https://open.spotify.com" in root_csp
            assert "https://www.dailymotion.com" in root_csp
            assert "https://www.linkedin.com" in root_csp
            assert "https://t.me" in root_csp
            assert "https://www.canva.com" in root_csp
            assert "https://www.threads.net" in root_csp
            assert "https://fonts.googleapis.com" in root_csp
            assert "https://fonts.gstatic.com" in root_csp
            assert "frame-ancestors 'none'" in root_csp

            admin_route = c.get("/admin")
            assert admin_route.status_code == 200
            assert 'id="root"' in admin_route.get_data(as_text=True)

            asset_resp = c.get("/assets/app-abc123.js")
            assert asset_resp.status_code == 200
            assert "immutable" in asset_resp.headers.get("Cache-Control", "")

            missing_asset = c.get("/assets/missing-999.js")
            assert missing_asset.status_code == 404

            blocked_av = c.get("/illegal.mp4")
            assert blocked_av.status_code == 404

            traversal = c.get("/../secret.txt")
            assert traversal.status_code in (400, 404)

            api_missing = c.get("/api/nonexistent-endpoint")
            assert api_missing.status_code == 404
            assert api_missing.is_json
            assert "default-src 'none'" in api_missing.headers.get("Content-Security-Policy", "")


@pytest.mark.unit
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
