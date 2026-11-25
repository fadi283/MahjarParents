"""Platform security middleware: HTTPS/HSTS, strict CORS, rate limiting, and env secrets."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import re
import threading
import time
from typing import Any, Callable
from urllib.parse import urlsplit

from flask import Response, g, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix

from cms_security import CMSValidationError, sanitize_plain_text

DEFAULT_DEV_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)
DEFAULT_CORS_ALLOWED_METHODS = ("GET", "POST", "PUT", "DELETE", "OPTIONS")
DEFAULT_CORS_ALLOWED_HEADERS = (
    "Authorization",
    "Content-Type",
    "If-None-Match",
    "X-Requested-With",
)
DEFAULT_CORS_EXPOSED_HEADERS = (
    "ETag",
    "X-Total-Count",
    "X-Has-More",
    "X-RateLimit-Limit",
    "X-RateLimit-Remaining",
    "X-RateLimit-Reset",
    "Retry-After",
)
DEFAULT_HTTPS_EXEMPT_PATHS = ("/api/health", "/api/ready")
FRONTEND_HTML_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "img-src 'self' https: data:; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "connect-src 'self' https:; "
    "frame-src 'self' https://docs.google.com https://www.youtube-nocookie.com "
    "https://player.vimeo.com https://w.soundcloud.com https://drive.google.com; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

_WEAK_SECRET_PREFIXES = (
    "dev",
    "secret",
    "changeme",
    "change-me",
    "default",
    "test",
    "replace",
    "example",
    "placeholder",
    "insecure",
    "mahjar-dev",
)
_WEAK_PASSWORDS = frozenset({
    "admin",
    "password",
    "password123",
    "changeme",
    "changeme123",
    "changeme123456",
    "123456",
    "12345678",
    "1234567890",
    "mahjar",
    "default",
    "qwerty",
})
_UNSAFE_HEADER_RE = re.compile(r"[\x00-\x1f\x7f\r\n]")
_ORIGIN_SPACE_RE = re.compile(r"[\s\x00-\x1f\x7f]")


class SecurityConfigError(RuntimeError):
    """Raised when environment or platform security configuration is invalid or unsafe."""


@dataclass(frozen=True)
class RateLimitDecision:
    """Result of evaluating a single rate-limit check."""

    allowed: bool
    limit: int
    remaining: int
    reset_at: int
    retry_after: int


def parse_bool(value: Any, default: bool = False) -> bool:
    """Parse boolean environment/config values strictly with a default fallback."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in ("1", "true", "yes", "on"):
        return True
    if normalized in ("0", "false", "no", "off"):
        return False
    return default


def parse_int(value: Any, default: int, *, min_value: int | None = None) -> int:
    """Parse integer environment/config values with optional lower bound."""
    if value is None or value == "":
        parsed = default
    else:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise SecurityConfigError(f"Expected integer config value, got {value!r}.") from exc
    if min_value is not None and parsed < min_value:
        raise SecurityConfigError(
            f"Config value {parsed} must be >= {min_value}."
        )
    return parsed


def parse_csv_list(value: Any) -> list[str]:
    """Parse a comma-separated string or iterable into stripped non-empty strings."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        raw_items = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_items = [str(item) for item in value]
    else:
        raise SecurityConfigError(f"Expected CSV string or sequence, got {type(value).__name__}.")
    return [item.strip() for item in raw_items if str(item).strip()]


def normalize_origin(raw_origin: Any) -> str:
    """Normalize an HTTP/HTTPS Origin header into lowercase 'scheme://host[:port]' or ''."""
    if not isinstance(raw_origin, str):
        return ""
    cleaned = raw_origin.strip()
    if not cleaned or cleaned.lower() == "null" or "*" in cleaned:
        return ""
    if _ORIGIN_SPACE_RE.search(cleaned):
        return ""

    parsed = urlsplit(cleaned)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return ""
    if parsed.username or parsed.password or not parsed.hostname:
        return ""
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return ""

    try:
        port = parsed.port
    except ValueError:
        return ""

    host = parsed.hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"

    is_default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    if port is not None and not is_default_port:
        return f"{scheme}://{host}:{port}"
    return f"{scheme}://{host}"


def parse_cors_origins(
    raw_origins: Any, *, allow_http: bool = True
) -> tuple[str, ...]:
    """Parse and validate strict CORS origins, rejecting wildcards, null, and paths."""
    items = parse_csv_list(raw_origins)
    normalized: list[str] = []
    seen: set[str] = set()

    for item in items:
        if item == "*" or "*" in item:
            raise SecurityConfigError("Wildcard '*' is not allowed in CORS_ALLOWED_ORIGINS.")
        if item.lower() == "null":
            raise SecurityConfigError("'null' is not allowed in CORS_ALLOWED_ORIGINS.")

        norm = normalize_origin(item)
        if not norm:
            raise SecurityConfigError(
                f"Invalid CORS origin '{item}'. Must be '<scheme>://<host>[:port]' without paths or queries."
            )
        if not allow_http and norm.startswith("http://"):
            raise SecurityConfigError(
                f"Insecure HTTP CORS origin '{item}' is disallowed in production."
            )
        if norm not in seen:
            seen.add(norm)
            normalized.append(norm)

    return tuple(normalized)


def validate_production_security_config(config: dict[str, Any]) -> None:
    """Fail fast on insecure cookie, CORS, secret-key, or admin credential configuration."""
    samesite = str(config.get("SESSION_COOKIE_SAMESITE") or "Lax")
    if samesite not in ("Lax", "Strict", "None"):
        raise SecurityConfigError(
            f"Invalid SESSION_COOKIE_SAMESITE '{samesite}'. Allowed: Lax, Strict, None."
        )
    if samesite == "None" and not bool(config.get("SESSION_COOKIE_SECURE")):
        raise SecurityConfigError(
            "SESSION_COOKIE_SAMESITE='None' requires SESSION_COOKIE_SECURE=True."
        )

    is_production = (
        str(config.get("MAHJAR_ENV") or "development").strip().lower() == "production"
        and not bool(config.get("TESTING"))
    )
    allow_http_cors = (not is_production) or bool(config.get("CORS_ALLOW_INSECURE_ORIGINS"))
    raw_cors = config.get("CORS_ALLOWED_ORIGINS", ())
    parsed_cors = parse_cors_origins(raw_cors, allow_http=allow_http_cors)
    config["CORS_ALLOWED_ORIGINS"] = parsed_cors

    if not is_production:
        return

    secret_key = str(config.get("SECRET_KEY") or "")
    secret_lower = secret_key.strip().lower()
    if len(secret_key) < 32 or any(
        secret_lower == prefix or secret_lower.startswith(f"{prefix}-") or secret_lower.startswith(f"{prefix}_")
        for prefix in _WEAK_SECRET_PREFIXES
    ):
        raise SecurityConfigError(
            "Production requires a strong MAHJAR_SECRET_KEY (at least 32 non-placeholder characters)."
        )

    pw_hash = str(config.get("ADMIN_PASSWORD_HASH") or "").strip()
    pw_plain = str(config.get("ADMIN_PASSWORD") or "")
    if not pw_hash and not pw_plain:
        raise SecurityConfigError(
            "Production requires MAHJAR_ADMIN_PASSWORD_HASH (or a strong MAHJAR_ADMIN_PASSWORD)."
        )
    if not pw_hash:
        pw_lower = pw_plain.strip().lower()
        if (
            len(pw_plain) < 12
            or pw_lower in _WEAK_PASSWORDS
            or pw_lower.startswith("changeme")
        ):
            raise SecurityConfigError(
                "Plaintext production ADMIN_PASSWORD must be at least 12 characters and non-default."
            )


class SlidingWindowRateLimiter:
    """Thread-safe, memory-bounded sliding-window in-memory rate limiter."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10000,
    ):
        self._clock = clock
        self._max_keys = max(1, int(max_keys))
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, str], deque[float]] = {}
        self._bucket_windows: dict[tuple[str, str], int] = {}

    def tracked_key_count(self) -> int:
        with self._lock:
            return len(self._buckets)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()
            self._bucket_windows.clear()

    def _evict_if_needed(self, now: float) -> None:
        if len(self._buckets) < self._max_keys:
            return
        expired_keys = [
            k
            for k, dq in self._buckets.items()
            if not dq or (now - dq[-1]) >= self._bucket_windows.get(k, 0)
        ]
        for k in expired_keys:
            self._buckets.pop(k, None)
            self._bucket_windows.pop(k, None)

        while len(self._buckets) >= self._max_keys:
            oldest_key = min(
                self._buckets,
                key=lambda k: self._buckets[k][-1] if self._buckets[k] else -1.0,
            )
            self._buckets.pop(oldest_key, None)
            self._bucket_windows.pop(oldest_key, None)

    def check(
        self,
        bucket: str,
        key: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        """Record/evaluate one request against `(bucket, key)` within `window_seconds`."""
        now_mono = float(self._clock())
        now_epoch = time.time()
        window = max(1, int(window_seconds))
        max_reqs = max(1, int(limit))
        cutoff = now_mono - window
        full_key = (bucket, key)

        with self._lock:
            dq = self._buckets.get(full_key)
            if dq is None:
                self._evict_if_needed(now_mono)
                dq = deque()
                self._buckets[full_key] = dq
            self._bucket_windows[full_key] = window

            while dq and dq[0] <= cutoff:
                dq.popleft()

            if len(dq) >= max_reqs:
                oldest = dq[0]
                retry_seconds = max(1, int((oldest + window - now_mono) + 0.9999))
                reset_epoch = int(now_epoch + retry_seconds)
                return RateLimitDecision(
                    allowed=False,
                    limit=max_reqs,
                    remaining=0,
                    reset_at=reset_epoch,
                    retry_after=retry_seconds,
                )

            dq.append(now_mono)
            remaining = max(0, max_reqs - len(dq))
            oldest = dq[0]
            reset_delta = max(1, int((oldest + window - now_mono) + 0.9999))
            return RateLimitDecision(
                allowed=True,
                limit=max_reqs,
                remaining=remaining,
                reset_at=int(now_epoch + reset_delta),
                retry_after=0,
            )


def sanitize_error_value(value: Any, max_length: int = 64) -> str:
    """Sanitize untrusted user values before reflecting them in JSON error messages."""
    if value is None:
        return ""
    try:
        cleaned = sanitize_plain_text(
            str(value),
            "input",
            required=False,
            max_length=max(max_length * 4, 256),
            allow_newlines=False,
        )
    except CMSValidationError:
        cleaned = ""
    cleaned = _UNSAFE_HEADER_RE.sub(" ", cleaned)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > max_length:
        return cleaned[: max_length - 1].rstrip() + "…"
    return cleaned


def validate_query_params(args: Any, *, max_length: int = 2048) -> None:
    """Reject query parameter keys or values containing NUL, CR/LF, or excessive length."""
    for key, values in args.lists():
        if "\x00" in key or "\r" in key or "\n" in key or len(key) > 128:
            raise CMSValidationError(
                "Invalid query parameter name.",
                status_code=400,
                code="INVALID_INPUT",
            )
        for val in values:
            if "\x00" in val or "\r" in val or "\n" in val:
                raise CMSValidationError(
                    f"Query parameter '{sanitize_error_value(key)}' contains illegal control characters.",
                    status_code=400,
                    code="INVALID_INPUT",
                    field=sanitize_error_value(key),
                )
            if len(val) > max_length:
                raise CMSValidationError(
                    f"Query parameter '{sanitize_error_value(key)}' exceeds maximum length.",
                    status_code=400,
                    code="INVALID_INPUT",
                    field=sanitize_error_value(key),
                )


def validate_json_structure(data: Any, *, max_depth: int = 8) -> None:
    """Reject overly nested JSON structures and NUL bytes in keys or string values."""
    stack: list[tuple[Any, int]] = [(data, 1)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, dict):
            if depth > max_depth:
                raise CMSValidationError(
                    f"JSON payload exceeds maximum nesting depth of {max_depth}.",
                    status_code=400,
                    code="INVALID_INPUT",
                )
            for k, v in node.items():
                if isinstance(k, str) and "\x00" in k:
                    raise CMSValidationError(
                        "JSON key contains illegal NUL byte.",
                        status_code=400,
                        code="INVALID_INPUT",
                    )
                stack.append((v, depth + 1))
        elif isinstance(node, list):
            if depth > max_depth:
                raise CMSValidationError(
                    f"JSON payload exceeds maximum nesting depth of {max_depth}.",
                    status_code=400,
                    code="INVALID_INPUT",
                )
            for item in node:
                stack.append((item, depth + 1))
        elif isinstance(node, str):
            if "\x00" in node:
                raise CMSValidationError(
                    "JSON string value contains illegal NUL byte.",
                    status_code=400,
                    code="INVALID_INPUT",
                )


def _classify_rate_limit_route(
    path: str, method: str, config: dict[str, Any]
) -> tuple[str, int, int] | None:
    upper_method = method.upper()
    if upper_method == "OPTIONS":
        return None
    if path in ("/api/admin/auth/login", "/api/admin/auth/logout") and upper_method == "POST":
        return (
            "auth",
            int(config.get("RATE_LIMIT_AUTH_REQUESTS", 10)),
            int(config.get("RATE_LIMIT_AUTH_WINDOW_SECONDS", 60)),
        )
    if path.startswith("/api/admin/") and upper_method in ("POST", "PUT", "PATCH", "DELETE"):
        return (
            "admin_write",
            int(config.get("RATE_LIMIT_WRITE_REQUESTS", 60)),
            int(config.get("RATE_LIMIT_WRITE_WINDOW_SECONDS", 60)),
        )
    if path == "/api/media/images" and upper_method == "POST":
        return (
            "media_upload",
            int(config.get("RATE_LIMIT_UPLOAD_REQUESTS", 20)),
            int(config.get("RATE_LIMIT_UPLOAD_WINDOW_SECONDS", 60)),
        )
    if path in ("/api/forms/validate", "/api/media/external") and upper_method == "POST":
        return (
            "public_write",
            int(config.get("RATE_LIMIT_PUBLIC_WRITE_REQUESTS", 30)),
            int(config.get("RATE_LIMIT_PUBLIC_WRITE_WINDOW_SECONDS", 60)),
        )
    return None


def _append_vary_headers(response: Response, tokens: tuple[str, ...]) -> None:
    existing_raw = response.headers.get("Vary")
    if not existing_raw:
        response.headers["Vary"] = ", ".join(tokens)
        return
    existing = [part.strip() for part in existing_raw.split(",") if part.strip()]
    existing_lower = {part.lower() for part in existing}
    for token in tokens:
        if token.lower() not in existing_lower:
            existing.append(token)
            existing_lower.add(token.lower())
    if existing:
        response.headers["Vary"] = ", ".join(existing)


def _build_https_redirect_url() -> str:
    safe_host = _UNSAFE_HEADER_RE.sub("", request.host or "localhost")
    safe_path = _UNSAFE_HEADER_RE.sub("", request.path or "/")
    if not safe_path.startswith("/"):
        safe_path = "/" + safe_path
    query_bytes = request.query_string or b""
    if query_bytes:
        query_str = _UNSAFE_HEADER_RE.sub("", query_bytes.decode("latin1"))
        return f"https://{safe_host}{safe_path}?{query_str}"
    return f"https://{safe_host}{safe_path}"


def configure_platform_security(
    flask_app: Any,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Attach ProxyFix, HTTPS enforcement, strict CORS, guardrails, rate limiter, and security headers."""
    validate_production_security_config(flask_app.config)

    trust_proxy_count = parse_int(
        flask_app.config.get("TRUST_PROXY_COUNT", 0), 0, min_value=0
    )
    if trust_proxy_count > 0:
        flask_app.wsgi_app = ProxyFix(
            flask_app.wsgi_app,
            x_for=trust_proxy_count,
            x_proto=trust_proxy_count,
            x_host=trust_proxy_count,
            x_prefix=trust_proxy_count,
        )

    effective_clock = flask_app.config.get("RATE_LIMIT_CLOCK") or clock
    max_keys = parse_int(
        flask_app.config.get("RATE_LIMIT_MAX_KEYS", 10000), 10000, min_value=1
    )
    limiter = SlidingWindowRateLimiter(clock=effective_clock, max_keys=max_keys)
    flask_app.extensions["rate_limiter"] = limiter

    allowed_origins_set = frozenset(flask_app.config.get("CORS_ALLOWED_ORIGINS") or ())
    allowed_methods = tuple(
        flask_app.config.get("CORS_ALLOWED_METHODS") or DEFAULT_CORS_ALLOWED_METHODS
    )
    allowed_methods_set = frozenset(m.upper() for m in allowed_methods)
    allowed_headers = tuple(
        flask_app.config.get("CORS_ALLOWED_HEADERS") or DEFAULT_CORS_ALLOWED_HEADERS
    )
    allowed_headers_lower = frozenset(h.lower() for h in allowed_headers)
    exposed_headers = tuple(
        flask_app.config.get("CORS_EXPOSED_HEADERS") or DEFAULT_CORS_EXPOSED_HEADERS
    )
    cors_max_age = parse_int(flask_app.config.get("CORS_MAX_AGE", 600), 600, min_value=0)
    exempt_https_paths = frozenset(
        flask_app.config.get("HTTPS_EXEMPT_PATHS") or DEFAULT_HTTPS_EXEMPT_PATHS
    )
    enforce_https = bool(flask_app.config.get("ENFORCE_HTTPS"))
    max_query_len = parse_int(
        flask_app.config.get("MAX_QUERY_PARAM_LENGTH", 2048), 2048, min_value=1
    )
    max_json_bytes = parse_int(
        flask_app.config.get("MAX_JSON_BODY_BYTES", 64 * 1024),
        64 * 1024,
        min_value=64,
    )
    max_json_depth = parse_int(
        flask_app.config.get("MAX_JSON_DEPTH", 8), 8, min_value=1
    )
    rate_limit_enabled = bool(flask_app.config.get("RATE_LIMIT_ENABLED", True))
    hsts_age = parse_int(
        flask_app.config.get("HSTS_MAX_AGE", 31536000), 31536000, min_value=0
    )
    hsts_header_val = f"max-age={hsts_age}; includeSubDomains"
    if bool(flask_app.config.get("HSTS_PRELOAD")):
        hsts_header_val += "; preload"

    @flask_app.before_request
    def _platform_security_before_request():
        g.cors_allowed_origin = None
        g.rate_limit_headers = None

        # 1. HTTPS enforcement
        if (
            enforce_https
            and not request.is_secure
            and request.path not in exempt_https_paths
        ):
            if request.method in ("GET", "HEAD"):
                redirect_resp = Response(status=301)
                redirect_resp.headers["Location"] = _build_https_redirect_url()
                redirect_resp.headers["Cache-Control"] = "no-store"
                return redirect_resp
            err_resp = jsonify({
                "error": "HTTPS is required for this endpoint.",
                "code": "HTTPS_REQUIRED",
            })
            err_resp.status_code = 403
            err_resp.headers["Cache-Control"] = "no-store"
            return err_resp

        # 2. Strict CORS & preflight handling
        raw_origin = request.headers.get("Origin")
        normalized_origin = normalize_origin(raw_origin) if raw_origin is not None else ""
        is_allowlisted = bool(normalized_origin and normalized_origin in allowed_origins_set)
        if is_allowlisted:
            g.cors_allowed_origin = normalized_origin

        if (
            request.method == "OPTIONS"
            and raw_origin is not None
            and request.headers.get("Access-Control-Request-Method")
        ):
            if not is_allowlisted:
                return (
                    jsonify({
                        "error": "CORS preflight origin is not allowed.",
                        "code": "CORS_ORIGIN_DENIED",
                    }),
                    403,
                )

            req_method = request.headers.get("Access-Control-Request-Method", "").strip().upper()
            if req_method not in allowed_methods_set:
                return (
                    jsonify({
                        "error": "Requested CORS method is not allowed.",
                        "code": "CORS_METHOD_NOT_ALLOWED",
                    }),
                    403,
                )

            req_headers_raw = request.headers.get("Access-Control-Request-Headers", "")
            req_headers = [h.strip().lower() for h in req_headers_raw.split(",") if h.strip()]
            if any(h not in allowed_headers_lower for h in req_headers):
                return (
                    jsonify({
                        "error": "Requested CORS header is not allowed.",
                        "code": "CORS_HEADER_NOT_ALLOWED",
                    }),
                    403,
                )

            preflight_resp = Response(status=204)
            preflight_resp.headers["Access-Control-Allow-Origin"] = normalized_origin
            preflight_resp.headers["Access-Control-Allow-Credentials"] = "true"
            preflight_resp.headers["Access-Control-Allow-Methods"] = ", ".join(allowed_methods)
            preflight_resp.headers["Access-Control-Allow-Headers"] = ", ".join(allowed_headers)
            preflight_resp.headers["Access-Control-Max-Age"] = str(cors_max_age)
            _append_vary_headers(
                preflight_resp,
                ("Origin", "Access-Control-Request-Method", "Access-Control-Request-Headers"),
            )
            return preflight_resp

        if raw_origin is not None and request.method in ("POST", "PUT", "PATCH", "DELETE"):
            same_origin = normalize_origin(f"{request.scheme}://{request.host}")
            is_same_origin = bool(normalized_origin and same_origin and normalized_origin == same_origin)
            if not is_allowlisted and not is_same_origin:
                return (
                    jsonify({
                        "error": "Cross-origin request denied.",
                        "code": "CORS_ORIGIN_DENIED",
                    }),
                    403,
                )

        # 3. Input guardrails (query params & JSON payloads)
        if request.args:
            validate_query_params(request.args, max_length=max_query_len)

        if request.method in ("POST", "PUT", "PATCH"):
            content_type = (request.mimetype or "").lower()
            if not content_type.startswith("multipart/form-data"):
                if request.content_length is not None and request.content_length > max_json_bytes:
                    return (
                        jsonify({
                            "error": "Request JSON payload exceeds the maximum allowed size.",
                            "code": "PAYLOAD_TOO_LARGE",
                        }),
                        413,
                    )
                raw_body = request.get_data(cache=True)
                if len(raw_body) > max_json_bytes:
                    return (
                        jsonify({
                            "error": "Request JSON payload exceeds the maximum allowed size.",
                            "code": "PAYLOAD_TOO_LARGE",
                        }),
                        413,
                    )
                if raw_body and (request.is_json or content_type == "application/json"):
                    parsed = request.get_json(silent=True)
                    if parsed is not None:
                        validate_json_structure(parsed, max_depth=max_json_depth)

        # 4. Rate limiting on auth and write routes
        if rate_limit_enabled:
            bucket_spec = _classify_rate_limit_route(
                request.path, request.method, flask_app.config
            )
            if bucket_spec is not None:
                bucket_name, limit_val, window_sec = bucket_spec
                client_key = request.remote_addr or "unknown"
                decision = limiter.check(
                    bucket_name,
                    client_key,
                    limit=limit_val,
                    window_seconds=window_sec,
                )
                g.rate_limit_headers = {
                    "X-RateLimit-Limit": str(decision.limit),
                    "X-RateLimit-Remaining": str(decision.remaining),
                    "X-RateLimit-Reset": str(decision.reset_at),
                }
                if not decision.allowed:
                    rl_resp = jsonify({
                        "error": "Too many requests. Please try again later.",
                        "code": "RATE_LIMIT_EXCEEDED",
                        "retryAfter": decision.retry_after,
                    })
                    rl_resp.status_code = 429
                    rl_resp.headers["Retry-After"] = str(decision.retry_after)
                    rl_resp.headers["Cache-Control"] = "no-store"
                    return rl_resp

        return None

    @flask_app.after_request
    def _platform_security_after_request(response: Response) -> Response:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), interest-cohort=()",
        )
        is_html_spa_response = (
            not request.path.startswith("/api/")
            and (response.mimetype or "").lower() == "text/html"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            FRONTEND_HTML_CSP
            if is_html_spa_response
            else "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")

        if request.path.startswith("/api/media/images/"):
            response.headers.setdefault("Cross-Origin-Resource-Policy", "cross-origin")
        elif request.path.startswith("/api/admin/"):
            response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        else:
            response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")

        if enforce_https or request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", hsts_header_val)

        if request.path.startswith("/api/admin/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"

        if request.path.startswith("/api/"):
            _append_vary_headers(response, ("Origin",))

        allowed_origin = getattr(g, "cors_allowed_origin", None)
        if allowed_origin:
            response.headers["Access-Control-Allow-Origin"] = allowed_origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers.setdefault(
                "Access-Control-Expose-Headers", ", ".join(exposed_headers)
            )

        rl_headers = getattr(g, "rate_limit_headers", None)
        if rl_headers:
            for h_name, h_val in rl_headers.items():
                response.headers[h_name] = h_val

        return response

    @flask_app.errorhandler(404)
    def handle_not_found(err):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Endpoint not found.", "code": "NOT_FOUND"}), 404
        return err

    @flask_app.errorhandler(405)
    def handle_method_not_allowed(err):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Method not allowed.", "code": "METHOD_NOT_ALLOWED"}), 405
        return err

    @flask_app.errorhandler(500)
    def handle_internal_error(_err):
        if request.path.startswith("/api/"):
            return (
                jsonify({
                    "error": "Internal server error.",
                    "code": "INTERNAL_SERVER_ERROR",
                }),
                500,
            )
        return Response("Internal server error.", status=500, mimetype="text/plain")
