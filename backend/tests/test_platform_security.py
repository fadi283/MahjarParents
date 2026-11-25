import io
import threading
import pytest
from werkzeug.security import generate_password_hash

import app as backend_app
import platform_security


class FakeClock:
    """Deterministic monotonic clock for rate-limiter unit and integration tests."""

    def __init__(self, initial: float = 1000.0):
        self.now = initial

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += seconds
        return self.now


def _make_png_bytes() -> bytes:
    import cv2
    import numpy as np

    img = np.zeros((32, 32, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", img)
    assert ok
    return encoded.tobytes()


@pytest.mark.unit
class TestCorsOriginParsingAndMatching:
    """Unit tests for strict CORS origin normalization and validation."""

    def test_parses_comma_separated_and_list_origins_with_normalization(self):
        parsed = platform_security.parse_cors_origins(
            " HTTPS://Mahjar.Vercel.App/ , https://admin.mahjar.org:8443 , https://mahjar.vercel.app "
        )
        assert parsed == (
            "https://mahjar.vercel.app",
            "https://admin.mahjar.org:8443",
        )

        from_list = platform_security.parse_cors_origins(
            ["https://One.Example.com", "http://localhost:3000"],
            allow_http=True,
        )
        assert from_list == (
            "https://one.example.com",
            "http://localhost:3000",
        )

        assert platform_security.parse_cors_origins("") == ()
        assert platform_security.parse_cors_origins([]) == ()

    @pytest.mark.parametrize(
        "bad_origin",
        [
            "*",
            "https://*",
            "null",
            "https://mahjar.vercel.app/admin",
            "https://mahjar.vercel.app?foo=bar",
            "https://mahjar.vercel.app#frag",
            "https://user:pass@mahjar.vercel.app",
            "ftp://mahjar.vercel.app",
            "javascript:alert(1)",
            "mahjar.vercel.app",
        ],
    )
    def test_rejects_wildcard_null_paths_queries_credentials_and_bad_schemes(
        self, bad_origin
    ):
        with pytest.raises(platform_security.SecurityConfigError):
            platform_security.parse_cors_origins(bad_origin, allow_http=True)

    def test_rejects_http_origins_when_allow_http_is_false(self):
        with pytest.raises(platform_security.SecurityConfigError):
            platform_security.parse_cors_origins(
                "http://mahjar.vercel.app", allow_http=False
            )


@pytest.mark.unit
class TestSlidingWindowRateLimiter:
    """Unit tests for thread-safe sliding-window in-memory rate limiting."""

    def test_enforces_limit_reports_metadata_and_resets_after_window(self):
        clock = FakeClock(500.0)
        limiter = platform_security.SlidingWindowRateLimiter(clock=clock, max_keys=100)

        d1 = limiter.check("auth", "1.2.3.4", limit=3, window_seconds=60)
        assert d1.allowed is True
        assert d1.limit == 3
        assert d1.remaining == 2

        clock.advance(10)
        d2 = limiter.check("auth", "1.2.3.4", limit=3, window_seconds=60)
        assert d2.allowed is True
        assert d2.remaining == 1

        clock.advance(10)
        d3 = limiter.check("auth", "1.2.3.4", limit=3, window_seconds=60)
        assert d3.allowed is True
        assert d3.remaining == 0

        # 4th request within 60s window is blocked
        d4 = limiter.check("auth", "1.2.3.4", limit=3, window_seconds=60)
        assert d4.allowed is False
        assert d4.remaining == 0
        assert d4.retry_after >= 1
        assert d4.reset_at >= 1

        # Separate bucket and separate client key remain unaffected
        other_bucket = limiter.check("write", "1.2.3.4", limit=3, window_seconds=60)
        other_ip = limiter.check("auth", "5.6.7.8", limit=3, window_seconds=60)
        assert other_bucket.allowed is True
        assert other_ip.allowed is True

        # Advance past earliest hit (t=500 + 60 = 560; current is 520 -> +41 = 561)
        clock.advance(41)
        d5 = limiter.check("auth", "1.2.3.4", limit=3, window_seconds=60)
        assert d5.allowed is True
        assert d5.remaining == 0

    def test_enforces_max_keys_memory_bound_and_thread_safety(self):
        clock = FakeClock(100.0)
        limiter = platform_security.SlidingWindowRateLimiter(clock=clock, max_keys=5)

        for i in range(12):
            res = limiter.check("write", f"10.0.0.{i}", limit=2, window_seconds=30)
            assert res.allowed is True
        assert limiter.tracked_key_count() <= 5

        # Concurrent stress check
        concurrent_limiter = platform_security.SlidingWindowRateLimiter(
            clock=clock, max_keys=100
        )
        results = []
        lock = threading.Lock()

        def worker():
            decision = concurrent_limiter.check("auth", "same-ip", limit=5, window_seconds=60)
            with lock:
                results.append(decision.allowed)

        threads = [threading.Thread(target=worker) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results.count(True) == 5
        assert results.count(False) == 7


@pytest.mark.unit
class TestEnvironmentSecretsValidation:
    """Unit tests for fail-fast production secret validation and dev defaults."""

    def test_production_rejects_missing_short_or_placeholder_secret_key(self):
        strong_hash = generate_password_hash("StrongMahjarAdmin!2026")
        for bad_secret in ("", "short-key", "dev-secret-key-with-more-than-32-chars", "changeme-" + "x" * 30):
            cfg = {
                "MAHJAR_ENV": "production",
                "TESTING": False,
                "SECRET_KEY": bad_secret,
                "ADMIN_PASSWORD_HASH": strong_hash,
                "ADMIN_PASSWORD": "",
                "SESSION_COOKIE_SAMESITE": "Lax",
                "SESSION_COOKIE_SECURE": True,
                "CORS_ALLOWED_ORIGINS": ("https://mahjar.vercel.app",),
            }
            with pytest.raises(platform_security.SecurityConfigError):
                platform_security.validate_production_security_config(cfg)

    def test_production_rejects_missing_or_weak_admin_credentials(self):
        strong_secret = "a9f8e7d6c5b4a39281706f5e4d3c2b1a0987654321"
        for bad_pw in ("", "admin", "short123", "changeme123456"):
            cfg = {
                "MAHJAR_ENV": "production",
                "TESTING": False,
                "SECRET_KEY": strong_secret,
                "ADMIN_PASSWORD_HASH": "",
                "ADMIN_PASSWORD": bad_pw,
                "SESSION_COOKIE_SAMESITE": "Lax",
                "SESSION_COOKIE_SECURE": True,
                "CORS_ALLOWED_ORIGINS": (),
            }
            with pytest.raises(platform_security.SecurityConfigError):
                platform_security.validate_production_security_config(cfg)

    def test_validates_cookie_samesite_and_wildcard_cors_in_all_envs(self):
        with pytest.raises(platform_security.SecurityConfigError):
            platform_security.validate_production_security_config({
                "MAHJAR_ENV": "development",
                "TESTING": False,
                "SECRET_KEY": "dev",
                "SESSION_COOKIE_SAMESITE": "None",
                "SESSION_COOKIE_SECURE": False,
                "CORS_ALLOWED_ORIGINS": (),
            })

        with pytest.raises(platform_security.SecurityConfigError):
            platform_security.validate_production_security_config({
                "MAHJAR_ENV": "development",
                "TESTING": False,
                "SECRET_KEY": "dev",
                "SESSION_COOKIE_SAMESITE": "Invalid",
                "SESSION_COOKIE_SECURE": False,
                "CORS_ALLOWED_ORIGINS": (),
            })

        with pytest.raises(platform_security.SecurityConfigError):
            platform_security.validate_production_security_config({
                "MAHJAR_ENV": "development",
                "TESTING": False,
                "SECRET_KEY": "dev",
                "SESSION_COOKIE_SAMESITE": "Lax",
                "SESSION_COOKIE_SECURE": False,
                "CORS_ALLOWED_ORIGINS": ("*",),
            })

    def test_accepts_strong_production_config_and_parses_secret_key_fallbacks(self):
        strong_secret = "b" * 48
        fallback1 = "c" * 48
        fallback2 = "d" * 48
        cfg = {
            "MAHJAR_ENV": "production",
            "TESTING": False,
            "SECRET_KEY": strong_secret,
            "SECRET_KEY_FALLBACKS": platform_security.parse_csv_list(
                f"{fallback1}, {fallback2}"
            ),
            "ADMIN_PASSWORD_HASH": generate_password_hash("StrongMahjarAdmin!2026"),
            "ADMIN_PASSWORD": "",
            "SESSION_COOKIE_SAMESITE": "Lax",
            "SESSION_COOKIE_SECURE": True,
            "CORS_ALLOWED_ORIGINS": ("https://mahjar.vercel.app",),
        }
        platform_security.validate_production_security_config(cfg)
        assert cfg["SECRET_KEY_FALLBACKS"] == [fallback1, fallback2]


@pytest.mark.unit
class TestInputGuardrailsHelpers:
    """Unit tests for deep JSON, query parameter, and error-reflection sanitization."""

    def test_validate_json_structure_rejects_excessive_depth_and_nul_bytes(self):
        ok_obj = {"a": [{"b": "safe"}]}
        platform_security.validate_json_structure(ok_obj, max_depth=8)

        deep_obj = {"k": 1}
        for _ in range(10):
            deep_obj = {"nested": deep_obj}
        with pytest.raises(platform_security.CMSValidationError) as depth_exc:
            platform_security.validate_json_structure(deep_obj, max_depth=8)
        assert depth_exc.value.status_code == 400
        assert depth_exc.value.code == "INVALID_INPUT"

        with pytest.raises(platform_security.CMSValidationError) as nul_exc:
            platform_security.validate_json_structure({"title": "bad\x00value"})
        assert nul_exc.value.code == "INVALID_INPUT"

    def test_validate_query_params_and_sanitize_error_value(self):
        from werkzeug.datastructures import MultiDict

        platform_security.validate_query_params(
            MultiDict([("category", "general"), ("limit", "10")]), max_length=128
        )

        for bad in (
            MultiDict([("category", "bad\x00val")]),
            MultiDict([("category", "bad\r\nval")]),
            MultiDict([("category", "a" * 200)]),
        ):
            with pytest.raises(platform_security.CMSValidationError) as exc_info:
                platform_security.validate_query_params(bad, max_length=128)
            assert exc_info.value.code == "INVALID_INPUT"

        cleaned = platform_security.sanitize_error_value(
            "<script>alert(1)</script>bad\r\nvalue", max_length=20
        )
        assert "<" not in cleaned
        assert ">" not in cleaned
        assert "\r" not in cleaned
        assert len(cleaned) <= 20


@pytest.mark.api
class TestHttpsEnforcementAndSecurityHeaders:
    """Integration tests for HTTPS enforcement, proxy trust, and security headers."""

    def test_enforces_https_redirect_for_get_and_403_for_mutations(
        self, tmp_path, admin_credentials
    ):
        secured_app = backend_app.create_app({
            "TESTING": True,
            "ENFORCE_HTTPS": True,
            "SESSION_COOKIE_SECURE": True,
            "HTTPS_EXEMPT_PATHS": ("/api/health",),
            "SECRET_KEY": "s" * 40,
            "ADMIN_USERNAME": admin_credentials["username"],
            "ADMIN_PASSWORD_HASH": generate_password_hash(admin_credentials["password"]),
            "CMS_DATA_FILE": str(tmp_path / "https.json"),
        })

        with secured_app.test_client() as client:
            # Exempt health route works over HTTP
            health = client.get("/api/health")
            assert health.status_code == 200

            # Non-exempt GET over HTTP redirects 301 to HTTPS with query string intact
            get_http = client.get("/api/posts?category=general")
            assert get_http.status_code == 301
            assert get_http.headers["Location"] == "https://localhost/api/posts?category=general"
            assert "no-store" in get_http.headers.get("Cache-Control", "")

            # Non-exempt POST over HTTP is rejected with 403 JSON
            post_http = client.post("/api/admin/auth/login", json=admin_credentials)
            assert post_http.status_code == 403
            assert post_http.get_json()["code"] == "HTTPS_REQUIRED"

            # Direct HTTPS request succeeds and sets HSTS + Secure cookie
            login_https = client.post(
                "/api/admin/auth/login",
                base_url="https://mahjar.example.com",
                json=admin_credentials,
            )
            assert login_https.status_code == 200
            assert "Secure" in login_https.headers.get("Set-Cookie", "")
            assert "max-age=" in login_https.headers.get("Strict-Transport-Security", "")
            assert "includeSubDomains" in login_https.headers.get(
                "Strict-Transport-Security", ""
            )

    def test_proxy_fix_honors_forwarded_proto_only_when_trusted(self, tmp_path):
        untrusted_app = backend_app.create_app({
            "TESTING": True,
            "ENFORCE_HTTPS": True,
            "TRUST_PROXY_COUNT": 0,
            "CMS_DATA_FILE": str(tmp_path / "untrusted.json"),
        })
        with untrusted_app.test_client() as c:
            spoofed = c.get("/api/committee", headers={"X-Forwarded-Proto": "https"})
            assert spoofed.status_code == 301

        trusted_app = backend_app.create_app({
            "TESTING": True,
            "ENFORCE_HTTPS": True,
            "TRUST_PROXY_COUNT": 1,
            "CMS_DATA_FILE": str(tmp_path / "trusted.json"),
        })
        with trusted_app.test_client() as c:
            proxied = c.get("/api/committee", headers={"X-Forwarded-Proto": "https"})
            assert proxied.status_code == 200
            assert "Strict-Transport-Security" in proxied.headers

    def test_applies_security_headers_on_public_admin_media_and_error_responses(
        self, client, admin_auth_headers
    ):
        public_resp = client.get("/api/committee")
        assert public_resp.status_code == 200
        assert public_resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert public_resp.headers.get("X-Frame-Options") == "DENY"
        assert (
            public_resp.headers.get("Referrer-Policy")
            == "strict-origin-when-cross-origin"
        )
        assert "geolocation=()" in public_resp.headers.get("Permissions-Policy", "")
        assert "frame-ancestors 'none'" in public_resp.headers.get(
            "Content-Security-Policy", ""
        )
        assert public_resp.headers.get("Cross-Origin-Opener-Policy") == "same-origin"
        # Not enforced on plain HTTP when ENFORCE_HTTPS is False
        assert "Strict-Transport-Security" not in public_resp.headers

        admin_resp = client.get("/api/admin/committee", headers=admin_auth_headers)
        assert admin_resp.status_code == 200
        assert admin_resp.headers.get("Cross-Origin-Resource-Policy") == "same-origin"
        assert "no-store" in admin_resp.headers.get("Cache-Control", "")

        upload_resp = client.post(
            "/api/media/images",
            data={"file": (io.BytesIO(_make_png_bytes()), "pic.png", "image/png")},
            content_type="multipart/form-data",
        )
        assert upload_resp.status_code == 201
        img_resp = client.get(upload_resp.get_json()["url"])
        assert img_resp.status_code == 200
        assert img_resp.headers.get("Cross-Origin-Resource-Policy") == "cross-origin"

        not_found = client.get("/api/does-not-exist")
        assert not_found.status_code == 404
        assert not_found.content_type == "application/json"
        assert not_found.headers.get("X-Content-Type-Options") == "nosniff"


@pytest.mark.api
class TestStrictCorsRules:
    """Integration tests for strict CORS origin allowlisting, preflight, and CSRF blocking."""

    def _make_cors_app(self, tmp_path, admin_credentials):
        return backend_app.create_app({
            "TESTING": True,
            "SECRET_KEY": "k" * 40,
            "ADMIN_USERNAME": admin_credentials["username"],
            "ADMIN_PASSWORD_HASH": generate_password_hash(admin_credentials["password"]),
            "CORS_ALLOWED_ORIGINS": ("https://mahjar.vercel.app",),
            "CMS_DATA_FILE": str(tmp_path / "cors.json"),
        })

    def test_allows_exact_allowlisted_origin_and_preflight_without_wildcard(
        self, tmp_path, admin_credentials
    ):
        cors_app = self._make_cors_app(tmp_path, admin_credentials)
        origin = "https://mahjar.vercel.app"

        with cors_app.test_client() as c:
            preflight = c.options(
                "/api/admin/posts",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "Authorization, Content-Type",
                },
            )
            assert preflight.status_code == 204
            assert preflight.headers.get("Access-Control-Allow-Origin") == origin
            assert preflight.headers.get("Access-Control-Allow-Credentials") == "true"
            assert "POST" in preflight.headers.get("Access-Control-Allow-Methods", "")
            assert "Authorization" in preflight.headers.get(
                "Access-Control-Allow-Headers", ""
            )
            assert "Origin" in preflight.headers.get("Vary", "")

            get_resp = c.get("/api/posts", headers={"Origin": origin})
            assert get_resp.status_code == 200
            assert get_resp.headers.get("Access-Control-Allow-Origin") == origin
            assert get_resp.headers.get("Access-Control-Allow-Credentials") == "true"
            expose = get_resp.headers.get("Access-Control-Expose-Headers", "")
            assert "ETag" in expose
            assert "X-Total-Count" in expose
            assert "Origin" in get_resp.headers.get("Vary", "")

            login_resp = c.post(
                "/api/admin/auth/login",
                headers={"Origin": origin},
                json=admin_credentials,
            )
            assert login_resp.status_code == 200
            assert login_resp.headers.get("Access-Control-Allow-Origin") == origin

    def test_rejects_disallowed_origins_methods_headers_and_cross_origin_mutations(
        self, tmp_path, admin_credentials
    ):
        cors_app = self._make_cors_app(tmp_path, admin_credentials)

        with cors_app.test_client() as c:
            for bad_origin in (
                "https://evil.example.com",
                "https://mahjar.vercel.app.evil.com",
                "null",
            ):
                preflight = c.options(
                    "/api/admin/posts",
                    headers={
                        "Origin": bad_origin,
                        "Access-Control-Request-Method": "POST",
                    },
                )
                assert preflight.status_code == 403
                assert "Access-Control-Allow-Origin" not in preflight.headers

                blocked_post = c.post(
                    "/api/admin/auth/login",
                    headers={"Origin": bad_origin},
                    json=admin_credentials,
                )
                assert blocked_post.status_code == 403
                assert blocked_post.get_json()["code"] == "CORS_ORIGIN_DENIED"
                assert "Access-Control-Allow-Origin" not in blocked_post.headers

            bad_method = c.options(
                "/api/admin/posts",
                headers={
                    "Origin": "https://mahjar.vercel.app",
                    "Access-Control-Request-Method": "TRACE",
                },
            )
            assert bad_method.status_code == 403

            bad_header = c.options(
                "/api/admin/posts",
                headers={
                    "Origin": "https://mahjar.vercel.app",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "X-Forbidden-Custom",
                },
            )
            assert bad_header.status_code == 403

            # Cross-origin GET from disallowed origin omits ACAO header
            disallowed_get = c.get(
                "/api/committee", headers={"Origin": "https://evil.example.com"}
            )
            assert disallowed_get.status_code == 200
            assert "Access-Control-Allow-Origin" not in disallowed_get.headers
            assert "Origin" in disallowed_get.headers.get("Vary", "")

    def test_allows_same_origin_post_even_when_cors_allowlist_is_empty(
        self, tmp_path, admin_credentials
    ):
        same_origin_app = backend_app.create_app({
            "TESTING": True,
            "SECRET_KEY": "k" * 40,
            "ADMIN_USERNAME": admin_credentials["username"],
            "ADMIN_PASSWORD_HASH": generate_password_hash(admin_credentials["password"]),
            "CORS_ALLOWED_ORIGINS": (),
            "CMS_DATA_FILE": str(tmp_path / "same_origin.json"),
        })
        with same_origin_app.test_client() as c:
            resp = c.post(
                "/api/admin/auth/login",
                base_url="https://school.example.org",
                headers={"Origin": "https://school.example.org"},
                json=admin_credentials,
            )
            assert resp.status_code == 200

    def test_dev_lan_origin_allowlist_permits_private_ip_dev_ports_only(
        self, tmp_path, admin_credentials
    ):
        assert platform_security.is_private_lan_dev_origin("http://10.0.0.5:3000") is True
        assert platform_security.is_private_lan_dev_origin("http://192.168.1.25:5173") is True
        assert platform_security.is_private_lan_dev_origin("http://8.8.8.8:3000") is False
        assert platform_security.is_private_lan_dev_origin("http://10.0.0.5:8080") is False
        assert platform_security.is_private_lan_dev_origin("https://evil.example.com") is False

        lan_dev_app = backend_app.create_app({
            "TESTING": True,
            "SECRET_KEY": "k" * 40,
            "ADMIN_USERNAME": admin_credentials["username"],
            "ADMIN_PASSWORD_HASH": generate_password_hash(admin_credentials["password"]),
            "CORS_ALLOWED_ORIGINS": platform_security.DEFAULT_DEV_CORS_ORIGINS,
            "CORS_ALLOW_DEV_LAN_ORIGINS": True,
            "CMS_DATA_FILE": str(tmp_path / "lan_dev.json"),
        })
        with lan_dev_app.test_client() as c:
            ok_resp = c.post(
                "/api/admin/auth/login",
                base_url="http://127.0.0.1:5000",
                headers={"Origin": "http://10.0.0.5:3000"},
                json=admin_credentials,
            )
            assert ok_resp.status_code == 200
            assert ok_resp.headers.get("Access-Control-Allow-Origin") == "http://10.0.0.5:3000"

            denied_resp = c.post(
                "/api/admin/auth/login",
                base_url="http://127.0.0.1:5000",
                headers={"Origin": "http://8.8.8.8:3000"},
                json=admin_credentials,
            )
            assert denied_resp.status_code == 403
            assert denied_resp.get_json()["code"] == "CORS_ORIGIN_DENIED"


@pytest.mark.api
class TestRateLimitingOnAuthAndWriteRoutes:
    """Integration tests for rate limiting on auth, admin write, upload, and public write routes."""

    def _make_limited_app(self, tmp_path, admin_credentials, clock, **overrides):
        cfg = {
            "TESTING": True,
            "SECRET_KEY": "r" * 40,
            "ADMIN_USERNAME": admin_credentials["username"],
            "ADMIN_PASSWORD_HASH": generate_password_hash(admin_credentials["password"]),
            "RATE_LIMIT_ENABLED": True,
            "RATE_LIMIT_AUTH_REQUESTS": 2,
            "RATE_LIMIT_AUTH_WINDOW_SECONDS": 60,
            "RATE_LIMIT_WRITE_REQUESTS": 3,
            "RATE_LIMIT_WRITE_WINDOW_SECONDS": 60,
            "RATE_LIMIT_UPLOAD_REQUESTS": 2,
            "RATE_LIMIT_UPLOAD_WINDOW_SECONDS": 60,
            "RATE_LIMIT_PUBLIC_WRITE_REQUESTS": 2,
            "RATE_LIMIT_PUBLIC_WRITE_WINDOW_SECONDS": 60,
            "RATE_LIMIT_CLOCK": clock,
            "CMS_DATA_FILE": str(tmp_path / "ratelimit.json"),
        }
        cfg.update(overrides)
        return backend_app.create_app(cfg)

    def test_rate_limits_auth_login_and_recovers_after_window(
        self, tmp_path, admin_credentials
    ):
        clock = FakeClock(2000.0)
        app = self._make_limited_app(tmp_path, admin_credentials, clock)

        with app.test_client() as c:
            # OPTIONS preflight should not consume auth rate limit quota
            preflight = c.options(
                "/api/admin/auth/login",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "POST",
                },
            )
            assert preflight.status_code == 204

            r1 = c.post(
                "/api/admin/auth/login",
                json={"username": "admin", "password": "wrong"},
            )
            assert r1.status_code == 401
            assert r1.headers.get("X-RateLimit-Limit") == "2"
            assert r1.headers.get("X-RateLimit-Remaining") == "1"

            r2 = c.post(
                "/api/admin/auth/login",
                json={"username": "admin", "password": "wrong"},
            )
            assert r2.status_code == 401
            assert r2.headers.get("X-RateLimit-Remaining") == "0"

            r3 = c.post("/api/admin/auth/login", json=admin_credentials)
            assert r3.status_code == 429
            body = r3.get_json()
            assert body["code"] == "RATE_LIMIT_EXCEEDED"
            assert body["retryAfter"] >= 1
            assert int(r3.headers["Retry-After"]) >= 1
            assert "no-store" in r3.headers.get("Cache-Control", "")

            # Different client IP still allowed
            other_ip = c.post(
                "/api/admin/auth/login",
                environ_base={"REMOTE_ADDR": "198.51.100.25"},
                json=admin_credentials,
            )
            assert other_ip.status_code == 200

            # Advance clock past window -> original IP recovers
            clock.advance(61)
            recovered = c.post("/api/admin/auth/login", json=admin_credentials)
            assert recovered.status_code == 200

    def test_rate_limits_admin_writes_uploads_and_public_writes_but_not_public_reads(
        self, tmp_path, admin_credentials
    ):
        clock = FakeClock(3000.0)
        app = self._make_limited_app(tmp_path, admin_credentials, clock)

        with app.test_client() as c:
            login_resp = c.post("/api/admin/auth/login", json=admin_credentials)
            assert login_resp.status_code == 200
            headers = {"Authorization": f"Bearer {login_resp.get_json()['token']}"}

            # 3 admin writes allowed, 4th blocked
            for idx in range(3):
                resp = c.post(
                    "/api/admin/posts",
                    headers=headers,
                    json={"title": f"منشور {idx}", "summary": "ملخص صالح"},
                )
                assert resp.status_code == 201
            blocked_write = c.post(
                "/api/admin/posts",
                headers=headers,
                json={"title": "منشور رابع", "summary": "ملخص صالح"},
            )
            assert blocked_write.status_code == 429
            assert blocked_write.get_json()["code"] == "RATE_LIMIT_EXCEEDED"

            # 2 uploads allowed, 3rd blocked
            png_bytes = _make_png_bytes()
            for _ in range(2):
                up = c.post(
                    "/api/media/images",
                    data={"file": (io.BytesIO(png_bytes), "img.png", "image/png")},
                    content_type="multipart/form-data",
                )
                assert up.status_code == 201
            blocked_up = c.post(
                "/api/media/images",
                data={"file": (io.BytesIO(png_bytes), "img.png", "image/png")},
                content_type="multipart/form-data",
            )
            assert blocked_up.status_code == 429

            # 2 public POST validations allowed, 3rd blocked
            for _ in range(2):
                val = c.post(
                    "/api/forms/validate",
                    json={"url": "https://forms.gle/fajYrbhcTA3xZa8d9"},
                )
                assert val.status_code == 200
            blocked_val = c.post(
                "/api/forms/validate",
                json={"url": "https://forms.gle/fajYrbhcTA3xZa8d9"},
            )
            assert blocked_val.status_code == 429

            # Public reads are never blocked by auth/write rate limiters
            for _ in range(20):
                assert c.get("/api/committee").status_code == 200
                assert c.get("/api/posts").status_code == 200
                assert c.get("/api/forms").status_code == 200
                assert c.get("/api/health").status_code == 200

    def test_spoofed_x_forwarded_for_ignored_when_trust_proxy_is_zero(
        self, tmp_path, admin_credentials
    ):
        clock = FakeClock(4000.0)
        app = self._make_limited_app(
            tmp_path, admin_credentials, clock, TRUST_PROXY_COUNT=0
        )
        with app.test_client() as c:
            for ip in ("1.1.1.1", "2.2.2.2"):
                r = c.post(
                    "/api/admin/auth/login",
                    headers={"X-Forwarded-For": ip},
                    json={"username": "admin", "password": "wrong"},
                )
                assert r.status_code == 401
            r3 = c.post(
                "/api/admin/auth/login",
                headers={"X-Forwarded-For": "3.3.3.3"},
                json={"username": "admin", "password": "wrong"},
            )
            assert r3.status_code == 429


@pytest.mark.api
class TestInputSanitizationHardening:
    """Integration tests for query/JSON guardrails, error reflection, and upload auth."""

    def test_sanitizes_reflected_invalid_query_values_and_blocks_crlf_and_nul(
        self, client
    ):
        xss_cat = client.get("/api/posts?category=<script>alert(1)</script>")
        assert xss_cat.status_code == 400
        err_text = xss_cat.get_json()["error"]
        assert "<script>" not in err_text.lower()
        assert "<" not in err_text

        xss_form = client.get("/api/forms?type=<img src=x onerror=alert(1)>")
        assert xss_form.status_code == 400
        assert "<img" not in xss_form.get_json()["error"].lower()

        nul_query = client.get("/api/posts?category=general%00")
        assert nul_query.status_code == 400
        assert nul_query.get_json()["code"] == "INVALID_INPUT"

        crlf_query = client.get("/api/posts?category=general%0d%0aSet-Cookie:evil=1")
        assert crlf_query.status_code == 400
        assert crlf_query.get_json()["code"] == "INVALID_INPUT"

    def test_enforces_json_depth_nul_bytes_body_size_and_entity_encoded_xss(
        self, tmp_path, admin_credentials
    ):
        app = backend_app.create_app({
            "TESTING": True,
            "SECRET_KEY": "z" * 40,
            "ADMIN_USERNAME": admin_credentials["username"],
            "ADMIN_PASSWORD_HASH": generate_password_hash(admin_credentials["password"]),
            "MAX_JSON_DEPTH": 4,
            "MAX_JSON_BODY_BYTES": 512,
            "CMS_DATA_FILE": str(tmp_path / "guard.json"),
        })
        with app.test_client() as c:
            token = c.post("/api/admin/auth/login", json=admin_credentials).get_json()[
                "token"
            ]
            headers = {"Authorization": f"Bearer {token}"}

            deep = {"title": "valid", "summary": "valid", "extra": {"a": {"b": {"c": {"d": 1}}}}}
            deep_resp = c.post("/api/admin/posts", headers=headers, json=deep)
            assert deep_resp.status_code == 400
            assert deep_resp.get_json()["code"] == "INVALID_INPUT"

            nul_resp = c.post(
                "/api/admin/posts",
                headers=headers,
                json={"title": "bad\x00title", "summary": "valid"},
            )
            assert nul_resp.status_code == 400
            assert nul_resp.get_json()["code"] == "INVALID_INPUT"

            oversized_resp = c.post(
                "/api/admin/posts",
                headers=headers,
                json={"title": "valid", "summary": "أ" * 600},
            )
            assert oversized_resp.status_code == 413
            assert oversized_resp.get_json()["code"] == "PAYLOAD_TOO_LARGE"

            encoded_xss = c.post(
                "/api/admin/posts",
                headers=headers,
                json={
                    "title": "إعلان &lt;script&gt;alert(1)&lt;/script&gt; هام",
                    "summary": "نص &#x6a;avascript:alert(1) نظيف",
                },
            )
            assert encoded_xss.status_code == 201
            created = encoded_xss.get_json()
            assert "<script>" not in created["title"].lower()
            assert "javascript:" not in created["summary"].lower()

            overlong_pw = c.post(
                "/api/admin/auth/login",
                json={"username": "admin", "password": "p" * 300},
            )
            assert overlong_pw.status_code == 400
            assert overlong_pw.get_json()["code"] == "INVALID_CREDENTIALS_FORMAT"


@pytest.mark.api
class TestFreeTierProductionBoot:
    """Integration tests for zero-budget/free-tier production environment configuration."""

    def test_production_env_boots_enforces_https_auth_uploads_and_hides_secrets(
        self, monkeypatch, tmp_path
    ):
        secret = "prod-free-tier-secret-key-at-least-48-chars-long!!"
        pw = "MahjarProdAdmin#2026"
        pw_hash = generate_password_hash(pw)

        monkeypatch.setenv("MAHJAR_ENV", "production")
        monkeypatch.setenv("MAHJAR_SECRET_KEY", secret)
        monkeypatch.setenv("MAHJAR_ADMIN_USERNAME", "committee_admin")
        monkeypatch.setenv("MAHJAR_ADMIN_PASSWORD_HASH", pw_hash)
        monkeypatch.setenv("MAHJAR_CORS_ALLOWED_ORIGINS", "https://mahjar.vercel.app")
        monkeypatch.setenv("MAHJAR_CMS_DATA_FILE", str(tmp_path / "prod.json"))
        monkeypatch.setenv("MAHJAR_MEDIA_UPLOAD_DIR", str(tmp_path / "prod_uploads"))

        prod_app = backend_app.create_app()
        assert prod_app.config["ENFORCE_HTTPS"] is True
        assert prod_app.config["SESSION_COOKIE_SECURE"] is True
        assert prod_app.config["TRUST_PROXY_COUNT"] == 1
        assert prod_app.config["REQUIRE_AUTH_FOR_MEDIA_UPLOAD"] is True
        assert prod_app.config["CORS_ALLOWED_ORIGINS"] == ("https://mahjar.vercel.app",)

        with prod_app.test_client() as c:
            # Health works even behind TLS-terminating free-tier proxy
            health = c.get("/api/health", headers={"X-Forwarded-Proto": "https"})
            assert health.status_code == 200
            assert secret not in health.get_data(as_text=True)

            # Unauthenticated image upload is blocked in production
            unauth_upload = c.post(
                "/api/media/images",
                headers={"X-Forwarded-Proto": "https"},
                data={"file": (io.BytesIO(_make_png_bytes()), "pic.png", "image/png")},
                content_type="multipart/form-data",
            )
            assert unauth_upload.status_code == 401

            # Authenticated upload succeeds over HTTPS proxy
            login = c.post(
                "/api/admin/auth/login",
                headers={
                    "X-Forwarded-Proto": "https",
                    "Origin": "https://mahjar.vercel.app",
                },
                json={"username": "committee_admin", "password": pw},
            )
            assert login.status_code == 200
            assert login.headers.get("Access-Control-Allow-Origin") == "https://mahjar.vercel.app"
            token = login.get_json()["token"]

            auth_upload = c.post(
                "/api/media/images",
                headers={
                    "X-Forwarded-Proto": "https",
                    "Authorization": f"Bearer {token}",
                },
                data={"file": (io.BytesIO(_make_png_bytes()), "pic.png", "image/png")},
                content_type="multipart/form-data",
            )
            assert auth_upload.status_code == 201
