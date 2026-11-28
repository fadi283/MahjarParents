import time
import pytest
from werkzeug.security import generate_password_hash

import cms_security


@pytest.mark.unit
@pytest.mark.security
class TestPlainTextSanitization:
    """Unit tests for strict XSS and plain-text sanitization helpers."""

    @pytest.mark.parametrize(
        "dirty, expected",
        [
            ("  أهلاً بكم في <b>مدرسة المحجر</b>  ", "أهلاً بكم في مدرسة المحجر"),
            ("إعلان<script>alert('xss')</script> هام", "إعلان هام"),
            ("نص <style>body{display:none}</style> نظيف", "نص نظيف"),
            ("محتوى <iframe src='https://evil.com'></iframe> آمن", "محتوى آمن"),
            ("صورة <img src=x onerror=alert(1)> توضيحية", "صورة توضيحية"),
            ("شعار <svg onload=alert(1)><path/></svg> المدرسة", "شعار المدرسة"),
            ("هجوم <scr<script>ipt>alert(1)</script> مزدوج", "هجوم مزدوج"),
            ("رابط javascript:alert(1) خبيث", "رابط alert(1) خبيث"),
            ("محارف\x00 تحكم \x07 مخفية \u202e عكسية", "محارف تحكم مخفية عكسية"),
            ("علامات < غير مغلقة > أو <script", "علامات غير مغلقة أو"),
            ("هجوم &lt;script&gt;alert(1)&lt;/script&gt; مشفر", "هجوم مشفر"),
            ("رابط &#x6a;avascript:alert(1) مشفر", "رابط alert(1) مشفر"),
            ("بيانات data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg== خبيثة", "بيانات خبيثة"),
        ],
    )
    def test_strips_xss_tags_scripts_and_control_characters(self, dirty, expected):
        cleaned = cms_security.sanitize_plain_text(dirty, "title", required=True)
        assert "<" not in cleaned
        assert ">" not in cleaned
        assert "javascript:" not in cleaned.lower()
        assert "\x00" not in cleaned
        assert "\u202e" not in cleaned
        assert cleaned == expected

    def test_preserves_newlines_only_when_allowed(self):
        raw = "السطر الأول\n\n<script>bad()</script>السطر الثاني"
        single_line = cms_security.sanitize_plain_text(raw, "summary", allow_newlines=False)
        multi_line = cms_security.sanitize_plain_text(raw, "summary", allow_newlines=True)

        assert single_line == "السطر الأول السطر الثاني"
        assert multi_line == "السطر الأول\nالسطر الثاني"

    def test_rejects_non_string_and_xss_only_required_values(self):
        with pytest.raises(cms_security.CMSValidationError) as non_str_exc:
            cms_security.sanitize_plain_text(12345, "title", required=True)
        assert non_str_exc.value.status_code == 400
        assert non_str_exc.value.code == "VALIDATION_ERROR"

        with pytest.raises(cms_security.CMSValidationError) as xss_only_exc:
            cms_security.sanitize_plain_text(
                "<script>alert(document.cookie)</script>", "title", required=True
            )
        assert xss_only_exc.value.status_code == 400
        assert xss_only_exc.value.field == "title"

    def test_enforces_min_and_max_length(self):
        with pytest.raises(cms_security.CMSValidationError) as short_exc:
            cms_security.sanitize_plain_text("أب", "title", required=True, min_length=3)
        assert short_exc.value.status_code == 400

        with pytest.raises(cms_security.CMSValidationError) as long_exc:
            cms_security.sanitize_plain_text("أ" * 21, "title", required=True, max_length=20)
        assert long_exc.value.status_code == 400


@pytest.mark.unit
@pytest.mark.security
class TestImageAndFieldValidation:
    """Unit tests for image URLs, email, phone, dates, integers, and booleans."""

    @pytest.mark.parametrize(
        "valid_url, expected",
        [
            (None, ""),
            ("", ""),
            ("   ", ""),
            ("/api/media/images/0123456789abcdef.webp", "/api/media/images/0123456789abcdef.webp"),
            ("/logo.jpg", "/logo.jpg"),
            ("https://cdn.example.com/school/photo.webp", "https://cdn.example.com/school/photo.webp"),
        ],
    )
    def test_accepts_safe_image_urls(self, valid_url, expected):
        assert cms_security.validate_image_url(valid_url) == expected

    @pytest.mark.parametrize(
        "bad_url",
        [
            "http://example.com/photo.jpg",
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "//evil.com/tracker.png",
            "/api/media/images/../../etc/passwd",
            "/api/media/images/%2e%2e/secret.webp",
            "https://example.com/icon.svg",
            "/uploads/badge.svg",
            "https://example.com/video.mp4",
            "https://example.com/audio.mp3",
            "https://user:pass@example.com/photo.webp",
            "https://example.com/photo.webp?x=<script>",
            "https://example.com/with space.jpg",
        ],
    )
    def test_rejects_unsafe_or_disallowed_image_urls(self, bad_url):
        with pytest.raises(cms_security.CMSValidationError) as exc_info:
            cms_security.validate_image_url(bad_url)
        assert exc_info.value.status_code == 400

    def test_validates_email_phone_dates_ints_and_booleans(self):
        assert cms_security.validate_email("") == ""
        assert cms_security.validate_email("  admin@mahjar.org  ") == "admin@mahjar.org"
        with pytest.raises(cms_security.CMSValidationError):
            cms_security.validate_email("not-an-email<script>")

        assert cms_security.validate_phone("") == ""
        assert cms_security.validate_phone(" 054-8856122 ") == "054-8856122"
        with pytest.raises(cms_security.CMSValidationError):
            cms_security.validate_phone("abc<script>")

        assert cms_security.validate_event_date("") == ""
        assert cms_security.validate_event_date("2026-12-05") == "2026-12-05"
        with pytest.raises(cms_security.CMSValidationError):
            cms_security.validate_event_date("2026-02-30")

        assert cms_security.validate_iso_timestamp("2026-11-24T10:30:00Z") == "2026-11-24T10:30:00Z"
        assert cms_security.validate_iso_timestamp("2026-11-24T12:30:00+02:00") == "2026-11-24T10:30:00Z"
        with pytest.raises(cms_security.CMSValidationError):
            cms_security.validate_iso_timestamp("not-a-timestamp")

        assert cms_security.validate_positive_int_field(3, "displayOrder") == 3
        with pytest.raises(cms_security.CMSValidationError):
            cms_security.validate_positive_int_field(True, "displayOrder")
        with pytest.raises(cms_security.CMSValidationError):
            cms_security.validate_positive_int_field(0, "displayOrder")

        assert cms_security.validate_bool_field(False, "active") is False
        with pytest.raises(cms_security.CMSValidationError):
            cms_security.validate_bool_field("true", "active")


@pytest.mark.unit
@pytest.mark.security
class TestGoogleFormsUrlValidation:
    """Unit tests for trusted Google Forms embed URL validation and normalization."""

    @pytest.mark.parametrize(
        "raw_url, expected_embed, expected_canonical, expected_id",
        [
            (
                "https://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQrStUvWxYz123456/viewform?usp=sf_link",
                "https://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQrStUvWxYz123456/viewform?embedded=true",
                "https://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQrStUvWxYz123456/viewform",
                "1FAIpQLScAbCdEfGhIjKlMnOpQrStUvWxYz123456",
            ),
            (
                "https://docs.google.com/forms/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/viewform",
                "https://docs.google.com/forms/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/viewform?embedded=true",
                "https://docs.google.com/forms/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/viewform",
                "1AbCdEfGhIjKlMnOpQrStUvWxYz",
            ),
            (
                "https://docs.google.com/forms/u/0/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQrStUvWxYz123456",
                "https://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQrStUvWxYz123456/viewform?embedded=true",
                "https://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQrStUvWxYz123456/viewform",
                "1FAIpQLScAbCdEfGhIjKlMnOpQrStUvWxYz123456",
            ),
            (
                "https://forms.gle/fajYrbhcTA3xZa8d9",
                "https://forms.gle/fajYrbhcTA3xZa8d9",
                "https://forms.gle/fajYrbhcTA3xZa8d9",
                "fajYrbhcTA3xZa8d9",
            ),
            (
                "https://forms.gle/fajYrbhcTA3xZa8d9/?usp=sf_link",
                "https://forms.gle/fajYrbhcTA3xZa8d9",
                "https://forms.gle/fajYrbhcTA3xZa8d9",
                "fajYrbhcTA3xZa8d9",
            ),
        ],
    )
    def test_normalizes_valid_google_forms_urls(
        self, raw_url, expected_embed, expected_canonical, expected_id
    ):
        result = cms_security.validate_google_forms_url(raw_url)
        assert result["provider"] == "google_forms"
        assert result["formId"] == expected_id
        assert result["embedUrl"] == expected_embed
        assert result["canonicalUrl"] == expected_canonical

    def test_preserves_only_safe_entry_prefill_query_parameters(self):
        raw = (
            "https://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQrStUvWxYz123456/viewform"
            "?usp=pp_url&entry.123456=الصف+الرابع&evil=ignored_param"
        )
        result = cms_security.validate_google_forms_url(raw)
        assert "embedded=true" in result["embedUrl"]
        assert "entry.123456=" in result["embedUrl"]
        assert "usp=" not in result["embedUrl"]
        assert "evil=" not in result["embedUrl"]
        assert "entry.123456=" in result["canonicalUrl"]
        assert "embedded=true" not in result["canonicalUrl"]

    @pytest.mark.parametrize(
        "bad_url, expected_code",
        [
            ("", "INVALID_FORM_URL"),
            ("http://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform", "INSECURE_FORM_URL"),
            ("javascript:alert(1)", "INSECURE_FORM_URL"),
            ("https://user:pass@docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform", "UNSAFE_FORM_URL"),
            ("https://docs.google.com:8443/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform", "UNSAFE_FORM_URL"),
            ("https://evil.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform", "UNTRUSTED_FORM_DOMAIN"),
            ("https://docs.google.com.evil.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform", "UNTRUSTED_FORM_DOMAIN"),
            ("http://forms.gle/fajYrbhcTA3xZa8d9", "INSECURE_FORM_URL"),
            ("https://forms.gle.evil.com/fajYrbhcTA3xZa8d9", "UNTRUSTED_FORM_DOMAIN"),
            ("https://sub.forms.gle/fajYrbhcTA3xZa8d9", "UNTRUSTED_FORM_DOMAIN"),
            ("https://forms.gle/", "INVALID_FORM_URL"),
            ("https://forms.gle/short", "INVALID_FORM_URL"),
            ("https://forms.gle/fajYrbhcTA3xZa8d9/extra", "INVALID_FORM_URL"),
            ("https://forms.gle:8443/fajYrbhcTA3xZa8d9", "UNSAFE_FORM_URL"),
            ("https://user:pass@forms.gle/fajYrbhcTA3xZa8d9", "UNSAFE_FORM_URL"),
            ("https://forms.gle/../../etc/passwd", "UNSAFE_FORM_URL"),
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "UNTRUSTED_FORM_DOMAIN"),
            ("https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQr/edit", "INVALID_FORM_URL"),
            ("https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQr/edit", "INVALID_FORM_URL"),
            ("https://docs.google.com/forms/d/e/short/viewform", "INVALID_FORM_URL"),
            ("https://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/../../etc/passwd", "UNSAFE_FORM_URL"),
            ("https://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform?x=<script>", "UNSAFE_FORM_URL"),
        ],
    )
    def test_rejects_untrusted_insecure_or_malformed_google_forms_urls(
        self, bad_url, expected_code
    ):
        with pytest.raises(cms_security.CMSValidationError) as exc_info:
            cms_security.validate_google_forms_url(bad_url)
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == expected_code


@pytest.mark.unit
@pytest.mark.security
class TestAdminAuthHelpers:
    """Unit tests for credential verification and signed token lifecycle."""

    def test_verifies_hashed_credentials_and_rejects_invalid_or_unconfigured(self):
        cfg = {
            "ADMIN_USERNAME": "admin",
            "ADMIN_PASSWORD_HASH": generate_password_hash("StrongPass!2026"),
            "ADMIN_PASSWORD": "",
        }
        assert cms_security.verify_admin_credentials(cfg, "admin", "StrongPass!2026") == "admin"

        with pytest.raises(cms_security.AdminAuthError) as bad_pw:
            cms_security.verify_admin_credentials(cfg, "admin", "WrongPass")
        assert bad_pw.value.status_code == 401
        assert bad_pw.value.code == "INVALID_CREDENTIALS"

        with pytest.raises(cms_security.AdminAuthError) as bad_user:
            cms_security.verify_admin_credentials(cfg, "other", "StrongPass!2026")
        assert bad_user.value.status_code == 401

        with pytest.raises(cms_security.AdminAuthError) as missing:
            cms_security.verify_admin_credentials(cfg, "", "StrongPass!2026")
        assert missing.value.status_code == 400
        assert missing.value.code == "MISSING_CREDENTIALS"

        unconfigured = {"ADMIN_USERNAME": "admin", "ADMIN_PASSWORD_HASH": "", "ADMIN_PASSWORD": ""}
        with pytest.raises(cms_security.AdminAuthError) as unconf:
            cms_security.verify_admin_credentials(unconfigured, "admin", "StrongPass!2026")
        assert unconf.value.status_code == 503
        assert unconf.value.code == "ADMIN_AUTH_NOT_CONFIGURED"

        with pytest.raises(cms_security.AdminAuthError) as overlong_pw:
            cms_security.verify_admin_credentials(cfg, "admin", "a" * 257)
        assert overlong_pw.value.status_code == 400
        assert overlong_pw.value.code == "INVALID_CREDENTIALS_FORMAT"

        with pytest.raises(cms_security.AdminAuthError) as ctrl_user:
            cms_security.verify_admin_credentials(cfg, "admin\x00", "StrongPass!2026")
        assert ctrl_user.value.status_code == 400
        assert ctrl_user.value.code == "INVALID_CREDENTIALS_FORMAT"

    def test_issues_verifies_expires_and_revokes_signed_tokens(self):
        secret = "super-secret-signing-key"
        token, jti = cms_security.issue_admin_token(secret, "admin")
        revoked: set[str] = set()

        payload = cms_security.verify_admin_token(secret, token, max_age=60, revoked_ids=revoked)
        assert payload["sub"] == "admin"
        assert payload["jti"] == jti

        # Tampered or wrong-secret token fails
        with pytest.raises(cms_security.AdminAuthError) as bad_sig:
            cms_security.verify_admin_token("wrong-secret", token, max_age=60, revoked_ids=revoked)
        assert bad_sig.value.status_code == 401
        assert bad_sig.value.code == "INVALID_TOKEN"

        # Revoked token fails
        revoked.add(jti)
        with pytest.raises(cms_security.AdminAuthError) as rev_exc:
            cms_security.verify_admin_token(secret, token, max_age=60, revoked_ids=revoked)
        assert rev_exc.value.status_code == 401
        assert rev_exc.value.code == "TOKEN_REVOKED"

        # Expired token fails
        time.sleep(1.1)
        with pytest.raises(cms_security.AdminAuthError) as exp_exc:
            cms_security.verify_admin_token(secret, token, max_age=0, revoked_ids=set())
        assert exp_exc.value.status_code == 401
        assert exp_exc.value.code == "TOKEN_EXPIRED"
