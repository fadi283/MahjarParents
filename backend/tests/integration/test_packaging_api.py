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


def _make_png_bytes(width: int = 32, height: int = 32, color=(20, 90, 160)) -> bytes:
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :] = color
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


@pytest.mark.integration
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


@pytest.mark.integration
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



class _FakePostgresCursor:
    """Adapter cursor returning dict rows compatible with psycopg dict_row."""

    def __init__(self, raw_cursor: sqlite3.Cursor):
        self._cur = raw_cursor
        self.description = raw_cursor.description
        self.rowcount = raw_cursor.rowcount

    def _to_dict(self, row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        return {key: row[key] for key in row.keys()}

    def fetchone(self):
        return self._to_dict(self._cur.fetchone())

    def fetchall(self):
        return [self._to_dict(r) for r in self._cur.fetchall()]


class _FakePostgresConnection:
    """In-memory SQLite-backed adapter emulating psycopg3 connections for tests."""

    def __init__(self, db_file: Path, *, fail_next_execute: bool = False):
        self._conn = sqlite3.connect(db_file, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self.closed = False
        self.broken = False
        self.fail_next_execute = fail_next_execute

    @staticmethod
    def _translate_sql(sql: str) -> str:
        translated = sql.replace("%s", "?")
        translated = translated.replace("TIMESTAMPTZ NOT NULL DEFAULT NOW()", "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")
        translated = translated.replace("BYTEA", "BLOB")
        return translated

    def execute(self, sql: str, params=()):
        if self.fail_next_execute:
            self.fail_next_execute = False
            raise sqlite3.OperationalError("server closed the connection unexpectedly")
        norm_params = tuple(
            int(p) if isinstance(p, bool) else p for p in params
        )
        cur = self._conn.execute(self._translate_sql(sql), norm_params)
        return _FakePostgresCursor(cur)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        if not self.closed:
            self.closed = True
            self._conn.close()


@pytest.mark.integration
@pytest.mark.api
class TestPostgresCMSStoreAndMediaPersistence:
    """Tests for Neon/PostgreSQL CMS persistence, DB-stored OpenCV images, reconnects, and migration."""

    def test_postgres_store_crud_reorder_reconnect_and_seed_once(self, tmp_path):
        pg_file = tmp_path / "fake_neon.db"
        conn_counter = {"count": 0}

        def _connect(_url: str):
            conn_counter["count"] += 1
            return _FakePostgresConnection(pg_file)

        store = cms_store.create_cms_store(
            backend_app.DEFAULT_COMMITTEE_MEMBERS,
            backend_app.DEFAULT_POSTS,
            cms_store.DEFAULT_GOOGLE_FORMS,
            storage_backend="postgres",
            database_url="postgres://neondb_owner:supersecret@ep-demo.neon.tech/neondb?sslmode=require",
            connect_fn=_connect,
        )
        assert isinstance(store, cms_store.PostgresCMSStore)

        info = store.storage_info()
        assert info["backend"] == "postgres"
        assert info["persisted"] is True
        assert info["counts"]["committee"] == len(backend_app.DEFAULT_COMMITTEE_MEMBERS)
        assert info["counts"]["posts"] == len(backend_app.DEFAULT_POSTS)
        assert info["counts"]["forms"] == len(cms_store.DEFAULT_GOOGLE_FORMS)
        assert "supersecret" not in json.dumps(info)
        assert "neon.tech" not in json.dumps(info)

        # Committee CRUD + reorder
        m1 = store.create_committee_member({
            "fullName": "عضو PostgreSQL",
            "role": "منسق",
            "responsibilitySummary": "متابعة دائمة.",
            "email": "pg@example.com",
            "phone": "0501112233",
            "avatarUrl": "",
            "isDirectContact": True,
        })
        assert m1["isDirectContact"] is True
        updated_m1 = store.update_committee_member(m1["id"], {"role": "منسق أول"})
        assert updated_m1["role"] == "منسق أول"
        reordered_c = store.reorder_committee([m1["id"]])
        assert reordered_c is not None

        # Posts + mediaLinks CRUD + reorder
        p1 = store.create_post(
            {
                "title": "منشور Neon دائم",
                "summary": "يبقى محفوظاً بعد إعادة التشغيل.",
                "category": "updates",
                "publishedAt": "2026-11-28T10:00:00Z",
                "eventDate": "",
                "imageUrl": "",
            },
            media_links=[
                {
                    "mediaType": "video",
                    "provider": "youtube",
                    "canonicalUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "embedUrl": "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
                    "originalUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "hostedExternally": True,
                    "title": "فيديو",
                }
            ],
        )
        assert len(p1["mediaLinks"]) == 1
        assert store.reorder_posts([p1["id"]]) is not None

        # Simulate Neon scale-to-zero idle disconnect -> transparent 1-time reconnect retry
        store._conn.fail_next_execute = True
        posts_after_reconnect = store.list_posts()
        assert any(p["id"] == p1["id"] for p in posts_after_reconnect)
        assert conn_counter["count"] >= 2

        # Standalone media link + forms CRUD
        standalone = store.create_media_link({
            "postId": None,
            "mediaType": "audio",
            "provider": "soundcloud",
            "canonicalUrl": "https://soundcloud.com/school/clip",
            "embedUrl": "https://w.soundcloud.com/player/?url=https%3A%2F%2Fsoundcloud.com%2Fschool%2Fclip",
            "originalUrl": "https://soundcloud.com/school/clip",
            "hostedExternally": True,
            "title": "صوت",
        })
        assert store.update_media_link(standalone["id"], {"title": "صوت محدث"})["title"] == "صوت محدث"
        assert store.delete_media_link(standalone["id"]) is True

        created_form = store.create_form({
            "formType": "feedback",
            "title": "نموذج دائم",
            "description": "وصف",
            "canonicalUrl": "https://docs.google.com/forms/d/e/1FAIpQLScPgTest001/viewform",
            "embedUrl": "https://docs.google.com/forms/d/e/1FAIpQLScPgTest001/viewform?embedded=true",
            "provider": "google_forms",
            "formId": "1FAIpQLScPgTest001",
            "active": True,
        })
        assert store.reorder_forms([created_form["id"]]) is not None

        # Delete every form and reopen -> defaults must NOT re-seed
        for form in store.list_forms():
            assert store.delete_form(form["id"]) is True
        store.close()

        reopened = cms_store.create_cms_store(
            backend_app.DEFAULT_COMMITTEE_MEMBERS,
            backend_app.DEFAULT_POSTS,
            cms_store.DEFAULT_GOOGLE_FORMS,
            database_url="postgresql://neondb_owner:supersecret@ep-demo.neon.tech/neondb?sslmode=require",
            connect_fn=_connect,
        )
        assert reopened.list_forms() == []
        assert reopened.get_post(p1["id"])["title"] == "منشور Neon دائم"
        assert reopened.delete_post(p1["id"]) is True
        assert reopened.delete_committee_member(m1["id"]) is True
        reopened.close()

    def test_flask_app_persists_cms_and_opencv_images_in_postgres_across_restarts(self, monkeypatch, tmp_path):
        pg_file = tmp_path / "app_neon.db"
        upload_dir = tmp_path / "empty_ephemeral_uploads"
        pw = "MahjarNeonPersist!2026"
        secret_db_url = "postgresql://neondb_owner:VerySecretPass99@ep-cool-host.neon.tech/neondb?sslmode=require"

        def _fake_open(self):
            return _FakePostgresConnection(pg_file)

        monkeypatch.setattr(cms_store.PostgresCMSStore, "_open_connection", _fake_open)
        monkeypatch.setenv("MAHJAR_ENV", "production")
        monkeypatch.setenv("MAHJAR_SECRET_KEY", "n" * 48)
        monkeypatch.setenv("MAHJAR_ADMIN_USERNAME", "admin")
        monkeypatch.setenv("MAHJAR_ADMIN_PASSWORD_HASH", generate_password_hash(pw))
        monkeypatch.setenv("MAHJAR_CORS_ALLOWED_ORIGINS", "https://mahjar-parents.vercel.app")
        monkeypatch.setenv("MAHJAR_STORAGE_BACKEND", "auto")
        monkeypatch.setenv("MAHJAR_DATABASE_URL", secret_db_url)
        monkeypatch.setenv("MAHJAR_MEDIA_UPLOAD_DIR", str(upload_dir))

        png_bytes = _make_png_bytes(80, 80, (30, 140, 210))
        opt = media_pipeline.optimize_image(png_bytes, filename="logo.png", content_type="image/png")

        app1 = backend_app.create_app()
        assert app1.extensions["cms_store"].storage_info()["backend"] == "postgres"

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
                data={"file": (io.BytesIO(png_bytes), "poster.png", "image/png")},
                content_type="multipart/form-data",
            )
            assert upload.status_code == 201
            image_url = upload.get_json()["url"]
            image_filename = upload.get_json()["filename"]

            # Nothing written to ephemeral local upload_dir
            assert not (upload_dir / image_filename).exists()

            # Idempotent re-upload succeeds
            dup_upload = c1.post(
                "/api/media/images",
                headers=headers,
                data={"file": (io.BytesIO(png_bytes), "poster.png", "image/png")},
                content_type="multipart/form-data",
            )
            assert dup_upload.status_code == 201

            # Raw A/V still rejected
            raw_av = c1.post(
                "/api/media/images",
                headers=headers,
                data={"file": (io.BytesIO(b"\x00\x00\x00\x18ftypmp42"), "bad.mp4", "video/mp4")},
                content_type="multipart/form-data",
            )
            assert raw_av.status_code == 415

            created_post = c1.post(
                "/api/admin/posts",
                headers=headers,
                json={
                    "title": "منشور محفوظ في Neon",
                    "summary": "الصورة والبيانات محفوظة في قاعدة البيانات.",
                    "category": "updates",
                    "imageUrl": image_url,
                },
            )
            assert created_post.status_code == 201

        # Simulate full Render container restart (fresh app, cleared caches, zero local files)
        app1.extensions["cms_store"].close()
        backend_app.clear_posts_cache()
        with backend_app._media_asset_cache_lock:
            backend_app._media_asset_cache.clear()

        app2 = backend_app.create_app()
        with app2.test_client() as c2:
            ready = c2.get("/api/ready", headers={"X-Forwarded-Proto": "https"})
            assert ready.status_code == 200
            ready_json = ready.get_json()
            assert ready_json["storage"]["backend"] == "postgres"
            assert ready_json["storage"]["persisted"] is True
            assert ready_json["media"]["assetCount"] == 1
            assert ready_json["media"]["usedBytes"] == opt["optimizedBytes"]
            assert "VerySecretPass99" not in ready.get_data(as_text=True)
            assert "ep-cool-host.neon.tech" not in ready.get_data(as_text=True)

            posts_resp = c2.get("/api/posts", headers={"X-Forwarded-Proto": "https"})
            assert posts_resp.status_code == 200
            assert any(p["title"] == "منشور محفوظ في Neon" for p in posts_resp.get_json())

            img_resp = c2.get(image_url, headers={"X-Forwarded-Proto": "https"})
            assert img_resp.status_code == 200
            assert img_resp.mimetype == "image/webp"
            assert len(img_resp.data) == opt["optimizedBytes"]

            missing_img = c2.get("/api/media/images/0123456789abcdef.webp", headers={"X-Forwarded-Proto": "https"})
            assert missing_img.status_code == 404

        app2.extensions["cms_store"].close()

        # Quota enforcement in Postgres media_assets
        quota_app = backend_app.create_app({
            "TESTING": True,
            "STORAGE_BACKEND": "postgres",
            "DATABASE_URL": secret_db_url,
            "MAX_MEDIA_STORAGE_BYTES": opt["optimizedBytes"] + 10,
        })
        with quota_app.test_client() as qc:
            other_png = _make_png_bytes(80, 80, (240, 20, 40))
            r_quota = qc.post(
                "/api/media/images",
                data={"file": (io.BytesIO(other_png), "second.png", "image/png")},
                content_type="multipart/form-data",
            )
            assert r_quota.status_code == 507
            assert r_quota.get_json()["code"] == "STORAGE_QUOTA_EXCEEDED"
        quota_app.extensions["cms_store"].close()

    def test_migrate_local_to_postgres_migrates_json_and_images(self, tmp_path):
        local_json = tmp_path / "cms_data.json"
        local_uploads = tmp_path / "uploads" / "images"
        local_uploads.mkdir(parents=True)

        local_store = cms_store.CMSStore(
            backend_app.DEFAULT_COMMITTEE_MEMBERS,
            backend_app.DEFAULT_POSTS,
            cms_store.DEFAULT_GOOGLE_FORMS,
            data_file=local_json,
        )
        local_store.create_post({
            "title": "منشور مرحّل إلى Neon",
            "summary": "محتوى محلي تم نقله.",
            "category": "general",
            "publishedAt": "2026-11-28T12:00:00Z",
            "eventDate": "",
            "imageUrl": "",
        })

        opt = media_pipeline.optimize_image(
            _make_png_bytes(48, 48, (90, 180, 60)),
            filename="avatar.png",
            content_type="image/png",
        )
        media_pipeline.save_optimized_image(opt, local_uploads)
        # Stray non-asset file should be ignored safely
        (local_uploads / "notes.txt").write_text("ignore", encoding="utf-8")

        pg_file = tmp_path / "migrated_neon.db"

        def _connect(_url: str):
            return _FakePostgresConnection(pg_file)

        summary = cms_store.migrate_local_to_postgres(
            local_json,
            "postgresql://user:pass@host/neondb?sslmode=require",
            uploads_dir=local_uploads,
            connect_fn=_connect,
        )
        assert summary["posts"] == len(local_store.list_posts())
        assert summary["mediaAssets"] == 1

        pg_store = cms_store.PostgresCMSStore(
            [],
            [],
            [],
            database_url="postgresql://user:pass@host/neondb?sslmode=require",
            connect_fn=_connect,
        )
        try:
            assert any(p["title"] == "منشور مرحّل إلى Neon" for p in pg_store.list_posts())
            asset = pg_store.get_media_asset(opt["filename"])
            assert asset is not None
            assert asset[0] == opt["data"]
            assert asset[1] == "image/webp"
        finally:
            pg_store.close()
