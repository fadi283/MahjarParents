"""Security, authentication, XSS sanitization, and URL allowlist helpers for Admin CMS."""

from __future__ import annotations

from datetime import datetime, timezone
import hmac
import html
import re
import secrets
import time
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash

from media_pipeline import RAW_AV_EXTENSIONS

ADMIN_TOKEN_SALT = "mahjar-admin-auth-v1"
DEFAULT_ADMIN_TOKEN_TTL_SECONDS = 3600

_CONTROL_CHARS_NO_NL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_CONTROL_CHARS_ALL_RE = re.compile(r"[\x00-\x1f\x7f]")
_BIDI_OVERRIDE_RE = re.compile(r"[\u202a-\u202e\u2066-\u2069]")
_DANGEROUS_BLOCK_RE = re.compile(
    r"<\s*(script|style|iframe|object|embed|svg)\b[^>]*>.*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_TAG_RE = re.compile(r"<\s*/?[a-zA-Z!][^<>]*>")
_UNCLOSED_TAG_RE = re.compile(r"<\s*/?[a-zA-Z!][^\s<>]*")
_DANGEROUS_SCHEME_RE = re.compile(
    r"(?:javascript|vbscript)\s*:|data\s*:\s*(?:text/html|image/svg\+xml|application/javascript)\b[^\s<>]*",
    re.IGNORECASE,
)
_UNSAFE_URL_CHARS_RE = re.compile(r"[\s\x00-\x1f\x7f<>\"']")

_EMAIL_RE = re.compile(r"^[^@\s<>\"']+@[^@\s<>\"']+\.[^@\s<>\"']+$")
_PHONE_RE = re.compile(r"^[0-9+\-\s()]{5,25}$")
_EVENT_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_GOOGLE_FORMS_HOST = "docs.google.com"
_GOOGLE_FORMS_SHORT_HOST = "forms.gle"
TRUSTED_GOOGLE_FORMS_DOMAINS = (_GOOGLE_FORMS_HOST, _GOOGLE_FORMS_SHORT_HOST)
_GOOGLE_FORMS_PATH_RE = re.compile(
    r"^/forms(?:/u/\d+)?/d/(?:(e)/)?([A-Za-z0-9_-]{10,})(?:/viewform)?/?$"
)
_GOOGLE_FORMS_SHORT_PATH_RE = re.compile(r"^/([A-Za-z0-9_-]{6,64})/?$")
_GOOGLE_FORMS_ENTRY_PARAM_RE = re.compile(r"^entry\.\d+$")


class CMSValidationError(ValueError):
    """Domain validation error for CMS payloads carrying HTTP status, code, and field."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        code: str = "VALIDATION_ERROR",
        field: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.field = field


class AdminAuthError(ValueError):
    """Authentication or authorization error for Admin CMS requests."""

    def __init__(
        self,
        message: str,
        status_code: int = 401,
        code: str = "UNAUTHORIZED",
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _strip_dangerous_markup(text: str) -> str:
    """Iteratively unescape HTML entities and remove dangerous blocks, tags, and script URIs."""
    cleaned = text
    for _ in range(5):
        previous = cleaned
        cleaned = html.unescape(cleaned)
        cleaned = _DANGEROUS_BLOCK_RE.sub(" ", cleaned)
        cleaned = _HTML_TAG_RE.sub(" ", cleaned)
        if cleaned == previous:
            break

    cleaned = _UNCLOSED_TAG_RE.sub(" ", cleaned)
    cleaned = _DANGEROUS_SCHEME_RE.sub("", cleaned)
    cleaned = cleaned.replace("<", " ").replace(">", " ")
    return cleaned


def sanitize_plain_text(
    value: Any,
    field_name: str,
    *,
    required: bool = False,
    min_length: int = 0,
    max_length: int = 500,
    allow_newlines: bool = False,
) -> str:
    """Sanitize plain text against XSS/HTML/control-char injection and enforce bounds."""
    if value is None:
        if required:
            raise CMSValidationError(
                f"Field '{field_name}' is required.",
                status_code=400,
                code="VALIDATION_ERROR",
                field=field_name,
            )
        return ""

    if not isinstance(value, str):
        raise CMSValidationError(
            f"Field '{field_name}' must be a string.",
            status_code=400,
            code="VALIDATION_ERROR",
            field=field_name,
        )

    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _BIDI_OVERRIDE_RE.sub("", normalized)
    if allow_newlines:
        normalized = _CONTROL_CHARS_NO_NL_RE.sub("", normalized)
    else:
        normalized = _CONTROL_CHARS_ALL_RE.sub(" ", normalized)

    stripped = _strip_dangerous_markup(normalized)

    if allow_newlines:
        lines = [" ".join(line.split()) for line in stripped.split("\n")]
        result = "\n".join(line for line in lines if line)
    else:
        result = " ".join(stripped.split())

    if required and not result:
        raise CMSValidationError(
            f"Field '{field_name}' cannot be empty after sanitization.",
            status_code=400,
            code="VALIDATION_ERROR",
            field=field_name,
        )

    if result and len(result) < min_length:
        raise CMSValidationError(
            f"Field '{field_name}' must be at least {min_length} characters.",
            status_code=400,
            code="VALIDATION_ERROR",
            field=field_name,
        )

    if len(result) > max_length:
        raise CMSValidationError(
            f"Field '{field_name}' must not exceed {max_length} characters.",
            status_code=400,
            code="VALIDATION_ERROR",
            field=field_name,
        )

    return result


def validate_email(value: Any, field_name: str = "email") -> str:
    """Validate optional email address string."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise CMSValidationError(
            f"Field '{field_name}' must be a string.",
            status_code=400,
            code="INVALID_EMAIL",
            field=field_name,
        )
    cleaned = value.strip()
    if not cleaned:
        return ""
    if (
        len(cleaned) > 254
        or _UNSAFE_URL_CHARS_RE.search(cleaned)
        or not _EMAIL_RE.match(cleaned)
    ):
        raise CMSValidationError(
            f"Field '{field_name}' is not a valid email address.",
            status_code=400,
            code="INVALID_EMAIL",
            field=field_name,
        )
    return cleaned


def validate_phone(value: Any, field_name: str = "phone") -> str:
    """Validate optional phone number string."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise CMSValidationError(
            f"Field '{field_name}' must be a string.",
            status_code=400,
            code="INVALID_PHONE",
            field=field_name,
        )
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        return ""
    if not _PHONE_RE.match(cleaned):
        raise CMSValidationError(
            f"Field '{field_name}' is not a valid phone number.",
            status_code=400,
            code="INVALID_PHONE",
            field=field_name,
        )
    return cleaned


def validate_iso_timestamp(value: Any, field_name: str = "publishedAt") -> str:
    """Validate ISO-8601 timestamp and normalize to UTC 'Z' format."""
    if not isinstance(value, str) or not value.strip():
        raise CMSValidationError(
            f"Field '{field_name}' must be a valid ISO-8601 timestamp.",
            status_code=400,
            code="INVALID_TIMESTAMP",
            field=field_name,
        )
    raw = value.strip()
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CMSValidationError(
            f"Field '{field_name}' must be a valid ISO-8601 timestamp.",
            status_code=400,
            code="INVALID_TIMESTAMP",
            field=field_name,
        ) from exc

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_event_date(value: Any, field_name: str = "eventDate") -> str:
    """Validate optional YYYY-MM-DD calendar date string."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise CMSValidationError(
            f"Field '{field_name}' must be a string in YYYY-MM-DD format.",
            status_code=400,
            code="INVALID_DATE",
            field=field_name,
        )
    cleaned = value.strip()
    if not cleaned:
        return ""
    if not _EVENT_DATE_RE.match(cleaned):
        raise CMSValidationError(
            f"Field '{field_name}' must be in YYYY-MM-DD format.",
            status_code=400,
            code="INVALID_DATE",
            field=field_name,
        )
    try:
        datetime.strptime(cleaned, "%Y-%m-%d")
    except ValueError as exc:
        raise CMSValidationError(
            f"Field '{field_name}' is not a valid calendar date.",
            status_code=400,
            code="INVALID_DATE",
            field=field_name,
        ) from exc
    return cleaned


def validate_positive_int_field(value: Any, field_name: str) -> int:
    """Validate a strict positive integer (>= 1), explicitly rejecting booleans."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CMSValidationError(
            f"Field '{field_name}' must be a positive integer (>= 1).",
            status_code=400,
            code="INVALID_INTEGER",
            field=field_name,
        )
    return value


def validate_bool_field(value: Any, field_name: str) -> bool:
    """Validate a strict boolean field."""
    if not isinstance(value, bool):
        raise CMSValidationError(
            f"Field '{field_name}' must be a boolean.",
            status_code=400,
            code="INVALID_BOOLEAN",
            field=field_name,
        )
    return value


def _get_path_extension(pathname: str) -> str:
    clean_path = (pathname or "").split("?", 1)[0].split("#", 1)[0]
    last_segment = clean_path.rsplit("/", 1)[-1]
    dot_idx = last_segment.rfind(".")
    if dot_idx <= 0:
        return ""
    return last_segment[dot_idx:].lower()


def _has_traversal_segments(pathname: str) -> bool:
    decoded = unquote(pathname or "")
    for candidate in (pathname or "", decoded):
        segments = candidate.replace("\\", "/").split("/")
        if "." in segments or ".." in segments:
            return True
    return False


def validate_image_url(raw_url: Any, field_name: str = "imageUrl") -> str:
    """Validate an optional image URL (HTTPS or safe root-relative path), rejecting SVG/AV/XSS."""
    if raw_url is None:
        return ""
    if not isinstance(raw_url, str):
        raise CMSValidationError(
            f"Field '{field_name}' must be a string.",
            status_code=400,
            code="INVALID_IMAGE_URL",
            field=field_name,
        )
    trimmed = raw_url.strip()
    if not trimmed:
        return ""

    if _UNSAFE_URL_CHARS_RE.search(trimmed):
        raise CMSValidationError(
            f"Field '{field_name}' contains unsafe URL characters.",
            status_code=400,
            code="UNSAFE_URL",
            field=field_name,
        )

    if trimmed.startswith("/"):
        if trimmed.startswith("//"):
            raise CMSValidationError(
                f"Field '{field_name}' cannot use protocol-relative URLs.",
                status_code=400,
                code="UNSAFE_URL",
                field=field_name,
            )
        path_only = trimmed.split("?", 1)[0].split("#", 1)[0]
        if _has_traversal_segments(path_only):
            raise CMSValidationError(
                f"Field '{field_name}' contains invalid path traversal segments.",
                status_code=400,
                code="UNSAFE_URL",
                field=field_name,
            )
        ext = _get_path_extension(path_only)
        if ext == ".svg" or ext in RAW_AV_EXTENSIONS:
            raise CMSValidationError(
                f"Field '{field_name}' uses a disallowed media extension '{ext}'.",
                status_code=400,
                code="UNSUPPORTED_MEDIA_TYPE",
                field=field_name,
            )
        return trimmed

    parsed = urlsplit(trimmed)
    if parsed.scheme.lower() != "https":
        raise CMSValidationError(
            f"Field '{field_name}' must use HTTPS or a safe relative path.",
            status_code=400,
            code="INSECURE_URL",
            field=field_name,
        )
    if parsed.username or parsed.password or not parsed.hostname:
        raise CMSValidationError(
            f"Field '{field_name}' is malformed or contains embedded credentials.",
            status_code=400,
            code="UNSAFE_URL",
            field=field_name,
        )
    if _has_traversal_segments(parsed.path):
        raise CMSValidationError(
            f"Field '{field_name}' contains invalid path traversal segments.",
            status_code=400,
            code="UNSAFE_URL",
            field=field_name,
        )
    ext = _get_path_extension(parsed.path)
    if ext == ".svg" or ext in RAW_AV_EXTENSIONS:
        raise CMSValidationError(
            f"Field '{field_name}' uses a disallowed media extension '{ext}'.",
            status_code=400,
            code="UNSUPPORTED_MEDIA_TYPE",
            field=field_name,
        )
    return trimmed


def validate_google_forms_url(
    raw_url: Any, field_name: str = "embedUrl"
) -> dict[str, str]:
    """Validate and normalize a Google Forms URL restricted strictly to docs.google.com/forms or forms.gle."""
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise CMSValidationError(
            "Google Forms URL must be a non-empty string.",
            status_code=400,
            code="INVALID_FORM_URL",
            field=field_name,
        )

    cleaned = raw_url.strip()
    if _UNSAFE_URL_CHARS_RE.search(cleaned):
        raise CMSValidationError(
            "Google Forms URL contains unsafe characters.",
            status_code=400,
            code="UNSAFE_FORM_URL",
            field=field_name,
        )

    parsed = urlsplit(cleaned)
    if parsed.scheme.lower() != "https":
        raise CMSValidationError(
            "Google Forms URL must use HTTPS.",
            status_code=400,
            code="INSECURE_FORM_URL",
            field=field_name,
        )

    if parsed.username or parsed.password:
        raise CMSValidationError(
            "Google Forms URL must not contain embedded credentials.",
            status_code=400,
            code="UNSAFE_FORM_URL",
            field=field_name,
        )

    try:
        port = parsed.port
    except ValueError as exc:
        raise CMSValidationError(
            "Google Forms URL has an invalid port.",
            status_code=400,
            code="UNSAFE_FORM_URL",
            field=field_name,
        ) from exc

    if port is not None:
        raise CMSValidationError(
            "Google Forms URL must not specify a custom port.",
            status_code=400,
            code="UNSAFE_FORM_URL",
            field=field_name,
        )

    host = (parsed.hostname or "").lower()
    if host not in TRUSTED_GOOGLE_FORMS_DOMAINS:
        raise CMSValidationError(
            f"Domain '{host}' is not a trusted Google Forms domain.",
            status_code=400,
            code="UNTRUSTED_FORM_DOMAIN",
            field=field_name,
        )

    if _has_traversal_segments(parsed.path):
        raise CMSValidationError(
            "Google Forms URL contains invalid path traversal segments.",
            status_code=400,
            code="UNSAFE_FORM_URL",
            field=field_name,
        )

    if host == _GOOGLE_FORMS_SHORT_HOST:
        short_match = _GOOGLE_FORMS_SHORT_PATH_RE.match(parsed.path)
        if not short_match:
            raise CMSValidationError(
                "URL does not match a valid shortened Google Forms path (forms.gle/<id>).",
                status_code=400,
                code="INVALID_FORM_URL",
                field=field_name,
            )
        short_code = short_match.group(1)
        canonical_short = f"https://{_GOOGLE_FORMS_SHORT_HOST}/{short_code}"
        return {
            "canonicalUrl": canonical_short,
            "embedUrl": canonical_short,
            "provider": "google_forms",
            "formId": short_code,
        }

    match = _GOOGLE_FORMS_PATH_RE.match(parsed.path)
    if not match:
        raise CMSValidationError(
            "URL does not match a valid Google Forms path (/forms/d/...).",
            status_code=400,
            code="INVALID_FORM_URL",
            field=field_name,
        )

    is_published_e = match.group(1) == "e"
    form_id = match.group(2)
    base_path = (
        f"/forms/d/e/{form_id}/viewform"
        if is_published_e
        else f"/forms/d/{form_id}/viewform"
    )

    safe_entries: list[tuple[str, str]] = []
    for key, val in parse_qsl(parsed.query, keep_blank_values=False):
        if _GOOGLE_FORMS_ENTRY_PARAM_RE.match(key):
            safe_val = sanitize_plain_text(val, key, required=False, max_length=200)
            if safe_val:
                safe_entries.append((key, safe_val))

    canonical_base = f"https://{_GOOGLE_FORMS_HOST}{base_path}"
    if safe_entries:
        encoded_entries = urlencode(safe_entries, quote_via=quote)
        canonical_url = f"{canonical_base}?{encoded_entries}"
        embed_url = f"{canonical_base}?embedded=true&{encoded_entries}"
    else:
        canonical_url = canonical_base
        embed_url = f"{canonical_base}?embedded=true"

    return {
        "canonicalUrl": canonical_url,
        "embedUrl": embed_url,
        "provider": "google_forms",
        "formId": form_id,
    }


def verify_admin_credentials(app_config: dict[str, Any], username: Any, password: Any) -> str:
    """Verify admin username/password against app configuration securely."""
    configured_username = str(app_config.get("ADMIN_USERNAME") or "admin").strip()
    password_hash = str(app_config.get("ADMIN_PASSWORD_HASH") or "").strip()
    configured_password = str(app_config.get("ADMIN_PASSWORD") or "")

    if not password_hash and not configured_password:
        raise AdminAuthError(
            "Admin authentication is not configured on the server.",
            status_code=503,
            code="ADMIN_AUTH_NOT_CONFIGURED",
        )

    if not isinstance(username, str) or not username.strip() or not isinstance(password, str) or not password:
        raise AdminAuthError(
            "Both 'username' and 'password' are required.",
            status_code=400,
            code="MISSING_CREDENTIALS",
        )

    if (
        len(username.strip()) > 128
        or len(password) > 256
        or _CONTROL_CHARS_ALL_RE.search(username)
        or _CONTROL_CHARS_ALL_RE.search(password)
    ):
        raise AdminAuthError(
            "Invalid credential format.",
            status_code=400,
            code="INVALID_CREDENTIALS_FORMAT",
        )

    username_ok = hmac.compare_digest(username.strip(), configured_username)
    if password_hash:
        password_ok = check_password_hash(password_hash, password)
    else:
        password_ok = hmac.compare_digest(password, configured_password)

    if not (username_ok and password_ok):
        raise AdminAuthError(
            "Invalid admin credentials.",
            status_code=401,
            code="INVALID_CREDENTIALS",
        )

    return configured_username


def issue_admin_token(secret_key: str, username: str) -> tuple[str, str]:
    """Issue a signed URL-safe timed admin Bearer token and its unique JTI."""
    jti = secrets.token_urlsafe(16)
    serializer = URLSafeTimedSerializer(secret_key, salt=ADMIN_TOKEN_SALT)
    token = serializer.dumps({"sub": username, "jti": jti, "iat": int(time.time())})
    return token, jti


def verify_admin_token(
    secret_key: str,
    token: str,
    *,
    max_age: int,
    revoked_ids: set[str],
) -> dict[str, Any]:
    """Verify signature, expiration, and revocation state of a Bearer admin token."""
    serializer = URLSafeTimedSerializer(secret_key, salt=ADMIN_TOKEN_SALT)
    try:
        payload = serializer.loads(token, max_age=max_age)
    except SignatureExpired as exc:
        raise AdminAuthError(
            "Admin authentication token has expired.",
            status_code=401,
            code="TOKEN_EXPIRED",
        ) from exc
    except BadSignature as exc:
        raise AdminAuthError(
            "Invalid admin authentication token.",
            status_code=401,
            code="INVALID_TOKEN",
        ) from exc

    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("sub"), str)
        or not payload["sub"].strip()
        or not isinstance(payload.get("jti"), str)
        or not payload["jti"].strip()
    ):
        raise AdminAuthError(
            "Invalid admin authentication token payload.",
            status_code=401,
            code="INVALID_TOKEN",
        )

    if payload["jti"] in revoked_ids:
        raise AdminAuthError(
            "Admin authentication token has been revoked.",
            status_code=401,
            code="TOKEN_REVOKED",
        )

    return payload


def authenticate_admin_request(
    flask_app: Any, request_obj: Any, session_obj: Any
) -> dict[str, Any]:
    """Authenticate an admin request via Bearer token or server-verified session cookie."""
    revoked_ids: set[str] = flask_app.extensions.setdefault("revoked_admin_ids", set())
    ttl_seconds = int(
        flask_app.config.get("ADMIN_TOKEN_TTL_SECONDS", DEFAULT_ADMIN_TOKEN_TTL_SECONDS)
    )
    secret_key = str(flask_app.config["SECRET_KEY"])

    auth_header = request_obj.headers.get("Authorization")
    if auth_header is not None:
        parts = auth_header.strip().split(None, 1)
        if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
            raise AdminAuthError(
                "Authorization header must use 'Bearer <token>'.",
                status_code=401,
                code="INVALID_TOKEN",
            )
        payload = verify_admin_token(
            secret_key,
            parts[1].strip(),
            max_age=ttl_seconds,
            revoked_ids=revoked_ids,
        )
        return {
            "username": payload["sub"],
            "authMethod": "bearer",
            "jti": payload["jti"],
        }

    if session_obj.get("admin_authenticated") is True:
        username = session_obj.get("admin_username")
        session_id = session_obj.get("admin_session_id")
        issued_at = session_obj.get("admin_issued_at")
        if (
            isinstance(username, str)
            and username.strip()
            and isinstance(session_id, str)
            and session_id.strip()
        ):
            if session_id in revoked_ids:
                raise AdminAuthError(
                    "Admin session has been revoked.",
                    status_code=401,
                    code="TOKEN_REVOKED",
                )
            if isinstance(issued_at, (int, float)) and (time.time() - issued_at) > ttl_seconds:
                raise AdminAuthError(
                    "Admin session has expired.",
                    status_code=401,
                    code="TOKEN_EXPIRED",
                )
            return {
                "username": username,
                "authMethod": "session",
                "sessionId": session_id,
            }

    raise AdminAuthError(
        "Admin authentication is required.",
        status_code=401,
        code="UNAUTHORIZED",
    )
