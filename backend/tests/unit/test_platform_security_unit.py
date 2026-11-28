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

@pytest.mark.unit
@pytest.mark.security
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
@pytest.mark.security
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
@pytest.mark.security
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
@pytest.mark.security
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

