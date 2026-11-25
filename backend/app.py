import copy
from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
import math
import os
import secrets
import threading
import time
from urllib.parse import urlsplit
from flask import (
    Flask,
    Response,
    abort,
    current_app,
    g,
    has_app_context,
    jsonify,
    request,
    send_from_directory,
    session,
)

from cms_security import (
    AdminAuthError,
    CMSValidationError,
    DEFAULT_ADMIN_TOKEN_TTL_SECONDS,
    TRUSTED_GOOGLE_FORMS_DOMAINS,
    authenticate_admin_request,
    issue_admin_token,
    sanitize_plain_text,
    validate_bool_field,
    validate_email,
    validate_event_date,
    validate_google_forms_url,
    validate_image_url,
    validate_iso_timestamp,
    validate_phone,
    validate_positive_int_field,
    verify_admin_credentials,
)
from cms_store import ALLOWED_FORM_TYPES, CMSStore, DEFAULT_GOOGLE_FORMS, create_cms_store
from media_pipeline import (
    DEFAULT_MAX_MEDIA_STORAGE_BYTES,
    DEFAULT_OUTPUT_FORMAT,
    MAX_IMAGE_HEIGHT,
    MAX_IMAGE_UPLOAD_BYTES,
    MAX_IMAGE_WIDTH,
    MediaValidationError,
    RAW_AV_EXTENSIONS,
    SAFE_ASSET_FILENAME_RE,
    inspect_media_storage,
    optimize_image,
    sanitize_external_media_links,
    save_optimized_image,
    validate_external_media_url,
)
from platform_security import (
    DEFAULT_CORS_ALLOWED_HEADERS,
    DEFAULT_CORS_ALLOWED_METHODS,
    DEFAULT_CORS_EXPOSED_HEADERS,
    DEFAULT_DEV_CORS_ORIGINS,
    DEFAULT_HTTPS_EXEMPT_PATHS,
    configure_platform_security,
    parse_bool,
    parse_csv_list,
    parse_int,
    sanitize_error_value,
)

COMMITTEE_CACHE_TTL_SECONDS = 300
POSTS_CACHE_TTL_SECONDS = 300
FORMS_CACHE_TTL_SECONDS = 300
MAX_CACHE_RESPONSE_ENTRIES = 256
MAX_CACHED_MEDIA_ASSET_BYTES = 256 * 1024
MAX_CACHED_MEDIA_ASSETS = 64
_media_asset_cache: dict[tuple[str, str], bytes] = {}
_media_asset_cache_lock = threading.Lock()
_spa_index_cache: dict[str, tuple[int, bytes]] = {}
_spa_index_cache_lock = threading.Lock()
_FORM_TYPE_PRIORITY = {
    "feedback": 1,
    "help_request": 2,
    "event_registration": 3,
}
POST_SUMMARY_MAX_LENGTH = 280
MAX_POSTS_LIMIT = 100
ALLOWED_POST_CATEGORIES = (
    "general",
    "upcoming_event",
    "student_activity",
    "updates",
)

DEFAULT_POSTS = [
    {
        "id": 1,
        "title": "يوم التراث والهوية في مدرسة المحجر الابتدائية",
        "summary": "يسر لجنة أولياء أمور الطلاب بالتعاون مع إدارة المدرسة دعوتكم للمشاركة في فعاليات يوم التراث السنوي، والذي يتضمن زوايا تراثية وعروضاً طلابية.",
        "category": "upcoming_event",
        "publishedAt": "2026-11-24T10:30:00Z",
        "eventDate": "2026-12-05",
        "imageUrl": "",
    },
    {
        "id": 2,
        "title": "مستجدات مشروع تظليل ساحة المدرسة (العريشة) وتنظيم حركة السير",
        "summary": "استمراراً لجهود اللجنة في توفير بيئة مدرسية آمنة ومريحة لأبنائنا، تم استكمال المرحلة الأولى من مشروع العريشة وتخصيص مسارات آمنة لخروج الطلاب.",
        "category": "updates",
        "publishedAt": "2026-11-22T16:45:00Z",
        "eventDate": "",
        "imageUrl": "",
    },
    {
        "id": 3,
        "title": "انطلاق مبادرة أصدقاء المكتبة والقراءة الحرة",
        "summary": "بدء الفعاليات الأسبوعية لتشجيع المطالعة والإبداع الأدبي لدى طلاب الصفوف الابتدائية، بإشراف طاقم اللغة العربية ودعم لجنة أولياء الأمور.",
        "category": "student_activity",
        "publishedAt": "2026-11-18T12:15:00Z",
        "eventDate": "",
        "imageUrl": "",
    },
    {
        "id": 4,
        "title": "تعميم هام للأهالي بخصوص مواعيد الدوام والسلامة المرورية",
        "summary": "نرجو من الأهالي الكرام الالتزام بمواعيد حضور وانصراف الطلاب، والتعاون مع المنظمين عند بوابة المدرسة حفاظاً على سلامة جميع الطلاب.",
        "category": "general",
        "publishedAt": "2026-11-10T08:00:00Z",
        "eventDate": "",
        "imageUrl": "",
    },
]

DEFAULT_COMMITTEE_MEMBERS = [
    {
        "id": 1,
        "fullName": "فادي وليد اغبارية",
        "phone": "0548856122",
        "email": "Egb.fadi@gmail.com",
        "role": "رئيس لجنة أولياء أمور الطلاب",
        "responsibilitySummary": "قيادة اللجنة وتمثيل الأهالي أمام الجهات الرسمية، والإشراف العام على المشاريع التربوية.",
        "avatarUrl": "",
        "displayOrder": 1,
    },
    {
        "id": 2,
        "fullName": "محمد شاكر إغبارية",
        "phone": "0507770794",
        "email": "",
        "role": "نائب الرئيس",
        "responsibilitySummary": "مساندة الرئيس والنيابة عنه، والإشراف على مشروع العريشة وتنظيم حركة السير عند انتهاء الدوام.",
        "avatarUrl": "",
        "displayOrder": 2,
    },
    {
        "id": 3,
        "fullName": "طه علي اغباريه",
        "isDirectContact": True,
        "phone": "0525308582",
        "email": "taha-igbaria@hotmail.com",
        "role": "أمين الصندوق ومسؤول التواصل مع الأهالي",
        "responsibilitySummary": "إدارة الشؤون المالية والميزانيات بشفافية، واستقبال توجهات ومقترحات الأهالي هاتفياً وإيصالها للجنة.",
        "avatarUrl": "",
        "displayOrder": 3,
    },
    {
        "id": 4,
        "fullName": "ايمن طه غازي",
        "phone": "0526006156",
        "email": "ayman1604@live.com",
        "role": "عضو لجنة ومنسّق فعاليات ومبادرات",
        "responsibilitySummary": "تخطيط وتنسيق الفعاليات اللامنهجية، وطرح المبادرات التربوية، والتواصل مع الأهالي لنقل احتياجات الطلاب.",
        "avatarUrl": "",
        "displayOrder": 4,
    },
    {
        "id": 5,
        "fullName": "رحمة حسن عسليه",
        "phone": "0532405337",
        "email": "rahmi.kiwan@gmail.com",
        "role": "عضو لجنة ومنسّق فعاليات ومبادرات",
        "responsibilitySummary": "تخطيط وتنسيق الفعاليات اللامنهجية، وطرح المبادرات التربوية، والتواصل مع الأهالي لنقل احتياجات الطلاب.",
        "avatarUrl": "",
        "displayOrder": 5,
    },
    {
        "id": 6,
        "fullName": "رائده مصاروه",
        "phone": "0523773415",
        "email": "",
        "role": "عضو لجنة ومنسّق فعاليات ومبادرات",
        "responsibilitySummary": "تخطيط وتنسيق الفعاليات اللامنهجية، وطرح المبادرات التربوية، والتواصل مع الأهالي لنقل احتياجات الطلاب.",
        "avatarUrl": "",
        "displayOrder": 6,
    },
    {
        "id": 7,
        "fullName": "غدير محاجنة",
        "phone": "0546670775",
        "email": "",
        "role": "عضو لجنة ومنسّق فعاليات ومبادرات",
        "responsibilitySummary": "تخطيط وتنسيق الفعاليات اللامنهجية، وطرح المبادرات التربوية، والتواصل مع الأهالي لنقل احتياجات الطلاب.",
        "avatarUrl": "",
        "displayOrder": 7,
    },
    {
        "id": 8,
        "fullName": "اماني علي جبارين",
        "phone": "0529583740",
        "email": "Jbareenzahi@gmail.com",
        "role": "عضو لجنة ومنسّق فعاليات ومبادرات",
        "responsibilitySummary": "تخطيط وتنسيق الفعاليات اللامنهجية، وطرح المبادرات التربوية، والتواصل مع الأهالي لنقل احتياجات الطلاب.",
        "avatarUrl": "",
        "displayOrder": 8,
    },
    {
        "id": 9,
        "fullName": "شموع طارق اغباريه",
        "phone": "0527314145",
        "email": "shomoa.1999@gmail.com",
        "role": "عضو لجنة ومنسّق فعاليات ومبادرات",
        "responsibilitySummary": "تخطيط وتنسيق الفعاليات اللامنهجية، وطرح المبادرات التربوية، والتواصل مع الأهالي لنقل احتياجات الطلاب.",
        "avatarUrl": "",
        "displayOrder": 9,
    },
    {
        "id": 10,
        "fullName": "هناء احمد محاميد",
        "phone": "0509221188",
        "email": "hnaa.khdoor@gmail.com",
        "role": "عضو لجنة ومنسّق فعاليات ومبادرات",
        "responsibilitySummary": "تخطيط وتنسيق الفعاليات اللامنهجية، وطرح المبادرات التربوية، والتواصل مع الأهالي لنقل احتياجات الطلاب.",
        "avatarUrl": "",
        "displayOrder": 10,
    },
    {
        "id": 11,
        "fullName": "حجازي محمد اغبارية",
        "phone": "0542777443",
        "email": "M.hejaze82@gmail.com",
        "role": "عضو لجنة ومنسّق فعاليات ومبادرات",
        "responsibilitySummary": "تمثيل الأهالي أمام اللجنة المحلية، وطرح المبادرات التربوية، والتواصل مع الأهالي لنقل احتياجات الطلاب.",
        "avatarUrl": "",
        "displayOrder": 11,
    },
    {
        "id": 12,
        "fullName": "حسن البنا محمد جبارين",
        "phone": "0526010093",
        "email": "Sweet.vanilla.gf@gmail.com",
        "role": "عضو لجنة ومنسّق فعاليات ومبادرات",
        "responsibilitySummary": "تخطيط وتنسيق الفعاليات اللامنهجية، وطرح المبادرات التربوية، والتواصل مع الأهالي لنقل احتياجات الطلاب.",
        "avatarUrl": "",
        "displayOrder": 12,
    },
]

_committee_cache = {
    "payload_bytes": None,
    "etag": None,
    "expires_at": 0.0,
    "store_id": None,
    "generation": 0,
}
_committee_cache_lock = threading.Lock()


def _cache_bounded_response(responses_dict: dict, cache_key, entry) -> None:
    """Insert a cached response entry while capping dictionary size for free-tier RAM."""
    if cache_key not in responses_dict and len(responses_dict) >= MAX_CACHE_RESPONSE_ENTRIES:
        oldest_key = next(iter(responses_dict))
        responses_dict.pop(oldest_key, None)
    responses_dict[cache_key] = entry


def _current_store_id():
    if has_app_context() and "cms_store" in current_app.extensions:
        return id(current_app.extensions["cms_store"])
    return None


def clear_committee_cache():
    """Invalidate the in-memory committee directory cache."""
    with _committee_cache_lock:
        _committee_cache["payload_bytes"] = None
        _committee_cache["etag"] = None
        _committee_cache["expires_at"] = 0.0
        _committee_cache["store_id"] = None
        _committee_cache["generation"] += 1


def load_committee_members():
    """Return raw committee member records from the active CMS store or defaults."""
    if has_app_context() and "cms_store" in current_app.extensions:
        return current_app.extensions["cms_store"].list_committee()
    return copy.deepcopy(DEFAULT_COMMITTEE_MEMBERS)


def _role_priority(role_text: str) -> int:
    """Assign hierarchical sort rank based on Arabic committee role titles."""
    normalized = (role_text or "").strip()
    if "نائب" in normalized:
        return 2
    if "رئيس" in normalized:
        return 1
    if "أمين الصندوق" in normalized or "امين الصندوق" in normalized:
        return 3
    return 4


def _normalize_and_order_committee_members(records):
    """Normalize field names (both camelCase and snake_case) and sort deterministically."""
    normalized_items = []
    for idx, raw in enumerate(records):
        member_id = raw.get("id", idx + 1)
        full_name = (raw.get("fullName") or raw.get("full_name") or "").strip()
        role = (raw.get("role") or raw.get("title") or "").strip()
        responsibility = (
            raw.get("responsibilitySummary")
            or raw.get("responsibility_summary")
            or ""
        ).strip()
        avatar_url = (raw.get("avatarUrl") or raw.get("avatar_url") or "").strip()
        email = (
            raw.get("email")
            or raw.get("contactUrl")
            or raw.get("contact_url")
            or ""
        ).strip()
        phone = (raw.get("phone") or "").strip()
        is_direct_contact = bool(
            raw.get("isDirectContact", raw.get("is_direct_contact", False))
        )

        explicit_order = raw.get("displayOrder", raw.get("display_order"))
        role_rank = _role_priority(role)
        has_explicit_order = explicit_order is not None
        sort_order_val = (
            int(explicit_order)
            if has_explicit_order
            else (role_rank * 1000 + int(member_id))
        )

        normalized_items.append(
            (
                (
                    0 if has_explicit_order else 1,
                    sort_order_val,
                    role_rank,
                    int(member_id),
                ),
                {
                    "id": member_id,
                    "fullName": full_name,
                    "full_name": full_name,
                    "role": role,
                    "responsibilitySummary": responsibility,
                    "responsibility_summary": responsibility,
                    "avatarUrl": avatar_url,
                    "avatar_url": avatar_url,
                    "email": email,
                    "phone": phone,
                    "isDirectContact": is_direct_contact,
                    "is_direct_contact": is_direct_contact,
                    "displayOrder": int(explicit_order)
                    if has_explicit_order
                    else None,
                    "display_order": int(explicit_order)
                    if has_explicit_order
                    else None,
                },
            )
        )

    normalized_items.sort(key=lambda pair: pair[0])

    ordered_records = []
    for position, (_, record) in enumerate(normalized_items, start=1):
        if record["displayOrder"] is None:
            record["displayOrder"] = position
            record["display_order"] = position
        ordered_records.append(record)

    return ordered_records


def _serialize_json_and_etag(data):
    """Serialize data into compact UTF-8 JSON bytes and compute a short quoted ETag."""
    payload_bytes = json.dumps(
        data, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    digest = hashlib.sha256(payload_bytes).hexdigest()[:16]
    return payload_bytes, f'"{digest}"'


def _build_cached_json_response(
    payload_bytes: bytes, etag: str, ttl_seconds: int, extra_headers=None
) -> Response:
    """Return a 200 JSON or 304 Not Modified response with Cache-Control and ETag headers."""
    headers = {
        "Cache-Control": f"public, max-age={ttl_seconds}, stale-while-revalidate=60",
        "ETag": etag,
    }
    if extra_headers:
        headers.update(extra_headers)

    if_none_match = request.headers.get("If-None-Match")
    if if_none_match and (
        if_none_match.strip() == etag or etag.strip('"') in if_none_match
    ):
        return Response(status=304, headers=headers)

    return Response(
        response=payload_bytes,
        status=200,
        mimetype="application/json",
        headers=headers,
    )


def _get_cached_committee_response():
    """Return (payload_bytes, etag) from in-memory cache or build and cache it."""
    with _committee_cache_lock:
        now = time.monotonic()
        store_id = _current_store_id()
        if (
            _committee_cache["payload_bytes"] is not None
            and _committee_cache["etag"] is not None
            and _committee_cache["store_id"] == store_id
            and now < _committee_cache["expires_at"]
        ):
            return _committee_cache["payload_bytes"], _committee_cache["etag"]

        raw_records = load_committee_members()
        ordered_records = _normalize_and_order_committee_members(raw_records)
        payload_bytes, etag = _serialize_json_and_etag(ordered_records)

        _committee_cache["payload_bytes"] = payload_bytes
        _committee_cache["etag"] = etag
        _committee_cache["expires_at"] = now + COMMITTEE_CACHE_TTL_SECONDS
        _committee_cache["store_id"] = store_id

        return payload_bytes, etag


_posts_cache = {
    "ordered_records": None,
    "responses": {},
    "expires_at": 0.0,
    "store_id": None,
    "generation": 0,
}
_posts_cache_lock = threading.Lock()


def clear_posts_cache():
    """Invalidate the in-memory announcements and events feed cache."""
    with _posts_cache_lock:
        _posts_cache["ordered_records"] = None
        _posts_cache["responses"] = {}
        _posts_cache["expires_at"] = 0.0
        _posts_cache["store_id"] = None
        _posts_cache["generation"] += 1


def load_posts():
    """Return raw announcement and event post records from the active CMS store or defaults."""
    if has_app_context() and "cms_store" in current_app.extensions:
        return current_app.extensions["cms_store"].list_posts()
    return copy.deepcopy(DEFAULT_POSTS)


def _parse_iso_timestamp(value: str) -> float:
    """Parse an ISO-8601 date/time string into a sortable POSIX timestamp."""
    raw = (value or "").strip()
    if not raw:
        return 0.0
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return 0.0


def _truncate_summary(text: str, max_length: int = POST_SUMMARY_MAX_LENGTH) -> str:
    """Keep feed payloads lightweight by bounding summary text length."""
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 1].rstrip() + "…"


def _normalize_and_order_posts(records):
    """Normalize post fields into lightweight feed objects ordered newest first."""
    normalized_items = []
    for idx, raw in enumerate(records):
        post_id = raw.get("id", idx + 1)
        title = (raw.get("title") or "").strip()
        raw_summary = (
            raw.get("summary")
            or raw.get("description")
            or raw.get("content")
            or ""
        )
        summary = _truncate_summary(raw_summary)
        category = (raw.get("category") or "general").strip() or "general"
        published_at = (
            raw.get("publishedAt")
            or raw.get("published_at")
            or raw.get("createdAt")
            or raw.get("created_at")
            or ""
        ).strip()
        event_date = (raw.get("eventDate") or raw.get("event_date") or "").strip()
        image_url = (raw.get("imageUrl") or raw.get("image_url") or "").strip()

        raw_media_links = list(raw.get("mediaLinks") or raw.get("media_links") or [])
        for legacy_key, legacy_type in (
            ("videoUrl", "video"),
            ("video_url", "video"),
            ("audioUrl", "audio"),
            ("audio_url", "audio"),
        ):
            legacy_val = (raw.get(legacy_key) or "").strip()
            if legacy_val:
                raw_media_links.append({"url": legacy_val, "mediaType": legacy_type})
        media_links = sanitize_external_media_links(
            raw_media_links,
            resolve_redirects=_should_resolve_short_media_urls(),
        )

        raw_order = raw.get("displayOrder", raw.get("display_order"))
        if isinstance(raw_order, int) and not isinstance(raw_order, bool) and raw_order >= 1:
            display_order = raw_order
        else:
            display_order = None

        timestamp = _parse_iso_timestamp(published_at)
        numeric_id = int(post_id) if str(post_id).isdigit() else idx + 1

        normalized_items.append(
            (
                (
                    0 if display_order is not None else 1,
                    display_order if display_order is not None else 0,
                    -timestamp,
                    -numeric_id,
                ),
                {
                    "id": post_id,
                    "title": title,
                    "summary": summary,
                    "category": category,
                    "publishedAt": published_at,
                    "published_at": published_at,
                    "eventDate": event_date,
                    "event_date": event_date,
                    "imageUrl": image_url,
                    "image_url": image_url,
                    "displayOrder": display_order,
                    "display_order": display_order,
                    "mediaLinks": media_links,
                },
            )
        )

    normalized_items.sort(key=lambda pair: pair[0])
    return [record for _, record in normalized_items]


def _get_cached_ordered_posts_with_generation():
    """Return (ordered_records, cache_generation) safely under the posts cache lock."""
    with _posts_cache_lock:
        now = time.monotonic()
        store_id = _current_store_id()
        if (
            _posts_cache["ordered_records"] is not None
            and _posts_cache["store_id"] == store_id
            and now < _posts_cache["expires_at"]
        ):
            return _posts_cache["ordered_records"], _posts_cache["generation"]

        raw_records = load_posts()
        ordered_records = _normalize_and_order_posts(raw_records)
        _posts_cache["ordered_records"] = ordered_records
        _posts_cache["responses"] = {}
        _posts_cache["expires_at"] = now + POSTS_CACHE_TTL_SECONDS
        _posts_cache["store_id"] = store_id
        _posts_cache["generation"] += 1
        return ordered_records, _posts_cache["generation"]


def _get_cached_ordered_posts():
    """Return normalized, newest-first posts list from in-memory cache or build it."""
    ordered_records, _ = _get_cached_ordered_posts_with_generation()
    return ordered_records


def _parse_positive_int(raw_value, param_name: str, allow_zero: bool = False):
    """Parse integer query parameters and return (value, error_message)."""
    if raw_value is None or raw_value == "":
        return None, None
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return None, f"Invalid '{param_name}' parameter: must be an integer."
    min_allowed = 0 if allow_zero else 1
    if parsed < min_allowed:
        comparator = ">= 0" if allow_zero else ">= 1"
        return None, f"Invalid '{param_name}' parameter: must be {comparator}."
    return parsed, None


def _format_committee_record(record: dict) -> dict:
    """Format a committee member record with both camelCase and snake_case keys."""
    display_order = record.get("displayOrder", record.get("display_order"))
    return {
        "id": record["id"],
        "fullName": record.get("fullName", ""),
        "full_name": record.get("fullName", ""),
        "role": record.get("role", ""),
        "responsibilitySummary": record.get("responsibilitySummary", ""),
        "responsibility_summary": record.get("responsibilitySummary", ""),
        "avatarUrl": record.get("avatarUrl", ""),
        "avatar_url": record.get("avatarUrl", ""),
        "email": record.get("email", ""),
        "phone": record.get("phone", ""),
        "isDirectContact": bool(
            record.get("isDirectContact", record.get("is_direct_contact", False))
        ),
        "is_direct_contact": bool(
            record.get("isDirectContact", record.get("is_direct_contact", False))
        ),
        "displayOrder": display_order,
        "display_order": display_order,
    }


def _format_post_record(record: dict) -> dict:
    """Format a post record with both camelCase and snake_case keys and media links."""
    display_order = record.get("displayOrder", record.get("display_order"))
    return {
        "id": record["id"],
        "title": record.get("title", ""),
        "summary": record.get("summary", ""),
        "category": record.get("category", "general"),
        "publishedAt": record.get("publishedAt", ""),
        "published_at": record.get("publishedAt", ""),
        "eventDate": record.get("eventDate", ""),
        "event_date": record.get("eventDate", ""),
        "imageUrl": record.get("imageUrl", ""),
        "image_url": record.get("imageUrl", ""),
        "displayOrder": display_order,
        "display_order": display_order,
        "mediaLinks": record.get("mediaLinks", []),
    }


def _format_form_record(record: dict) -> dict:
    """Format a Google Form configuration record with camelCase and snake_case keys."""
    canonical_url = record.get("canonicalUrl", "")
    embed_url = record.get("embedUrl", "")
    form_id = record.get("formId", "")
    display_order = record.get("displayOrder")
    return {
        "id": record["id"],
        "formType": record.get("formType", ""),
        "form_type": record.get("formType", ""),
        "title": record.get("title", ""),
        "description": record.get("description", ""),
        "embedUrl": embed_url,
        "embed_url": embed_url,
        "canonicalUrl": canonical_url,
        "canonical_url": canonical_url,
        "directUrl": canonical_url,
        "direct_url": canonical_url,
        "provider": record.get("provider", "google_forms"),
        "formId": form_id,
        "form_id": form_id,
        "active": bool(record.get("active", True)),
        "displayOrder": display_order,
        "display_order": display_order,
    }


_forms_cache = {
    "active_records": None,
    "responses": {},
    "expires_at": 0.0,
    "store_id": None,
    "generation": 0,
}
_forms_cache_lock = threading.Lock()


def clear_forms_cache():
    """Invalidate the in-memory active Google Forms configuration cache."""
    with _forms_cache_lock:
        _forms_cache["active_records"] = None
        _forms_cache["responses"] = {}
        _forms_cache["expires_at"] = 0.0
        _forms_cache["store_id"] = None
        _forms_cache["generation"] += 1


def load_forms():
    """Return raw Google Forms config records from the active CMS store or defaults."""
    if has_app_context() and "cms_store" in current_app.extensions:
        return current_app.extensions["cms_store"].list_forms()
    return copy.deepcopy(DEFAULT_GOOGLE_FORMS)


def _normalize_and_filter_active_forms(records):
    """Validate trusted Google Forms URLs, filter to active entries, sanitize, and order."""
    normalized_items = []
    for idx, raw in enumerate(records):
        if not isinstance(raw, dict):
            continue

        if raw.get("active", True) is not True:
            continue

        raw_type = raw.get("formType") if "formType" in raw else raw.get("form_type")
        form_type = (raw_type if isinstance(raw_type, str) else "").strip()
        if form_type not in ALLOWED_FORM_TYPES:
            continue

        raw_url = (
            raw.get("embedUrl")
            or raw.get("embed_url")
            or raw.get("canonicalUrl")
            or raw.get("canonical_url")
            or raw.get("url")
            or ""
        )
        try:
            validated_url = validate_google_forms_url(raw_url, field_name="embedUrl")
            title = sanitize_plain_text(
                raw.get("title"), "title", required=True, min_length=1, max_length=200
            )
        except CMSValidationError:
            continue

        try:
            description = sanitize_plain_text(
                raw.get("description"),
                "description",
                required=False,
                max_length=500,
                allow_newlines=True,
            )
        except CMSValidationError:
            description = ""

        raw_order = raw.get("displayOrder", raw.get("display_order"))
        if isinstance(raw_order, int) and not isinstance(raw_order, bool) and raw_order >= 1:
            display_order = raw_order
        else:
            display_order = None

        record_id = raw.get("id", idx + 1)
        numeric_id = int(record_id) if str(record_id).isdigit() else idx + 1
        sort_key = (
            0 if display_order is not None else 1,
            display_order if display_order is not None else 9999,
            _FORM_TYPE_PRIORITY.get(form_type, 99),
            numeric_id,
        )

        formatted = _format_form_record(
            {
                "id": record_id,
                "formType": form_type,
                "title": title,
                "description": description,
                "embedUrl": validated_url["embedUrl"],
                "canonicalUrl": validated_url["canonicalUrl"],
                "provider": validated_url["provider"],
                "formId": validated_url["formId"],
                "active": True,
                "displayOrder": display_order,
            }
        )
        normalized_items.append((sort_key, formatted))

    normalized_items.sort(key=lambda pair: pair[0])
    return [record for _, record in normalized_items]


def _get_cached_active_forms_with_generation():
    """Return (active_records, cache_generation) safely under the forms cache lock."""
    with _forms_cache_lock:
        now = time.monotonic()
        store_id = _current_store_id()
        if (
            _forms_cache["active_records"] is not None
            and _forms_cache["store_id"] == store_id
            and now < _forms_cache["expires_at"]
        ):
            return _forms_cache["active_records"], _forms_cache["generation"]

        raw_records = load_forms()
        active_records = _normalize_and_filter_active_forms(raw_records)
        _forms_cache["active_records"] = active_records
        _forms_cache["responses"] = {}
        _forms_cache["expires_at"] = now + FORMS_CACHE_TTL_SECONDS
        _forms_cache["store_id"] = store_id
        _forms_cache["generation"] += 1
        return active_records, _forms_cache["generation"]


def _get_cached_active_forms():
    """Return normalized, active, trusted Google Forms list from cache or build it."""
    active_records, _ = _get_cached_active_forms_with_generation()
    return active_records


def _build_public_forms_response(form_type: str, envelope_flag: bool) -> Response:
    """Build cached HTTP JSON/304 response for public Google Forms endpoints."""
    active_forms, generation = _get_cached_active_forms_with_generation()
    filter_key = form_type if form_type and form_type != "all" else "all"
    cache_key = (filter_key, envelope_flag)

    with _forms_cache_lock:
        cached_entry = (
            _forms_cache["responses"].get(cache_key)
            if _forms_cache["generation"] == generation
            else None
        )

    if cached_entry is not None:
        payload_bytes, etag, total_count = cached_entry
    else:
        if filter_key == "all":
            filtered = active_forms
        else:
            filtered = [form for form in active_forms if form["formType"] == filter_key]

        total_count = len(filtered)
        if envelope_flag:
            by_type = {ft: [] for ft in ALLOWED_FORM_TYPES}
            for item in filtered:
                by_type.setdefault(item["formType"], []).append(item)
            response_data = {
                "items": filtered,
                "byType": by_type,
                "allowedFormTypes": list(ALLOWED_FORM_TYPES),
                "trustedDomains": list(TRUSTED_GOOGLE_FORMS_DOMAINS),
                "total": total_count,
            }
        else:
            response_data = filtered

        payload_bytes, etag = _serialize_json_and_etag(response_data)
        with _forms_cache_lock:
            if _forms_cache["generation"] == generation:
                _cache_bounded_response(
                    _forms_cache["responses"],
                    cache_key,
                    (payload_bytes, etag, total_count),
                )

    return _build_cached_json_response(
        payload_bytes,
        etag,
        FORMS_CACHE_TTL_SECONDS,
        extra_headers={"X-Total-Count": str(total_count)},
    )


def _require_json_object() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise CMSValidationError(
            "Request body must be a valid JSON object.",
            status_code=400,
            code="INVALID_JSON",
        )
    return payload


def _parse_committee_payload(payload: dict, partial: bool = False) -> dict:
    """Validate and sanitize committee member fields for create or update."""
    record: dict = {}

    if not partial or "fullName" in payload or "full_name" in payload:
        raw_name = payload.get("fullName") if "fullName" in payload else payload.get("full_name")
        record["fullName"] = sanitize_plain_text(
            raw_name, "fullName", required=True, min_length=2, max_length=120
        )

    if not partial or "role" in payload or "title" in payload:
        raw_role = payload.get("role") if "role" in payload else payload.get("title")
        record["role"] = sanitize_plain_text(
            raw_role, "role", required=True, min_length=2, max_length=120
        )

    if not partial or "responsibilitySummary" in payload or "responsibility_summary" in payload:
        raw_resp = (
            payload.get("responsibilitySummary")
            if "responsibilitySummary" in payload
            else payload.get("responsibility_summary")
        )
        record["responsibilitySummary"] = sanitize_plain_text(
            raw_resp, "responsibilitySummary", required=False, max_length=500
        )

    if not partial or "email" in payload:
        record["email"] = validate_email(payload.get("email"), "email")

    if not partial or "phone" in payload:
        record["phone"] = validate_phone(payload.get("phone"), "phone")

    if "isDirectContact" in payload or "is_direct_contact" in payload:
        raw_flag = (
            payload.get("isDirectContact")
            if "isDirectContact" in payload
            else payload.get("is_direct_contact")
        )
        if not isinstance(raw_flag, bool):
            raise CMSValidationError(
                "isDirectContact must be a boolean.", field="isDirectContact"
            )
        record["isDirectContact"] = raw_flag
    elif not partial:
        record["isDirectContact"] = False

    if not partial or "avatarUrl" in payload or "avatar_url" in payload:
        raw_avatar = payload.get("avatarUrl") if "avatarUrl" in payload else payload.get("avatar_url")
        record["avatarUrl"] = validate_image_url(raw_avatar, "avatarUrl")

    if "displayOrder" in payload or "display_order" in payload:
        raw_order = payload.get("displayOrder") if "displayOrder" in payload else payload.get("display_order")
        if raw_order is None:
            record["displayOrder"] = None
        else:
            record["displayOrder"] = validate_positive_int_field(raw_order, "displayOrder")
    elif not partial:
        record["displayOrder"] = None

    if partial and not record:
        raise CMSValidationError(
            "At least one updatable field must be provided.",
            status_code=400,
            code="EMPTY_UPDATE",
        )

    return record


def _should_resolve_short_media_urls() -> bool:
    if not has_app_context():
        return False
    if current_app.config.get("RESOLVE_SHORT_MEDIA_URLS"):
        return True
    return not bool(current_app.config.get("TESTING"))


def _parse_media_link_entry(raw_item, default_type: str | None = None) -> dict:
    """Strictly validate and normalize a single external media link item."""
    if isinstance(raw_item, str):
        raw_url = raw_item
        requested_type = default_type
        title = ""
    elif isinstance(raw_item, dict):
        raw_url = (
            raw_item.get("url")
            or raw_item.get("originalUrl")
            or raw_item.get("original_url")
            or raw_item.get("canonicalUrl")
            or raw_item.get("canonical_url")
            or raw_item.get("embedUrl")
            or raw_item.get("embed_url")
            or ""
        )
        requested_type = raw_item.get("mediaType") or raw_item.get("media_type") or default_type
        title = sanitize_plain_text(
            raw_item.get("title"), "title", required=False, max_length=160
        )
    else:
        raise CMSValidationError(
            "Each media link entry must be a URL string or an object.",
            status_code=400,
            code="INVALID_MEDIA_LINK",
            field="mediaLinks",
        )

    normalized = validate_external_media_url(
        raw_url,
        media_type=requested_type,
        resolve_redirects=_should_resolve_short_media_urls(),
    )
    normalized["title"] = title
    return normalized


def _parse_post_payload(payload: dict, partial: bool = False) -> tuple[dict, list[dict] | None]:
    """Validate and sanitize post fields and optional external media links."""
    record: dict = {}
    media_links: list[dict] | None = None

    if not partial or "title" in payload:
        record["title"] = sanitize_plain_text(
            payload.get("title"), "title", required=True, min_length=2, max_length=200
        )

    if not partial or "summary" in payload or "description" in payload or "content" in payload:
        raw_summary = (
            payload.get("summary")
            if "summary" in payload
            else (payload.get("description") if "description" in payload else payload.get("content"))
        )
        record["summary"] = sanitize_plain_text(
            raw_summary,
            "summary",
            required=not partial,
            max_length=1000,
            allow_newlines=True,
        )

    if not partial or "category" in payload:
        raw_category = payload.get("category")
        category = (raw_category if isinstance(raw_category, str) else "").strip()
        if not category and not partial:
            category = "general"
        if category not in ALLOWED_POST_CATEGORIES:
            safe_cat = sanitize_error_value(raw_category)
            raise CMSValidationError(
                f"Invalid category '{safe_cat}'. Allowed: {', '.join(ALLOWED_POST_CATEGORIES)}.",
                status_code=400,
                code="INVALID_CATEGORY",
                field="category",
            )
        record["category"] = category

    if "publishedAt" in payload or "published_at" in payload:
        raw_pub = payload.get("publishedAt") if "publishedAt" in payload else payload.get("published_at")
        record["publishedAt"] = validate_iso_timestamp(raw_pub, "publishedAt")
    elif not partial:
        record["publishedAt"] = (
            datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        )

    if not partial or "eventDate" in payload or "event_date" in payload:
        raw_event = payload.get("eventDate") if "eventDate" in payload else payload.get("event_date")
        record["eventDate"] = validate_event_date(raw_event, "eventDate")

    if not partial or "imageUrl" in payload or "image_url" in payload:
        raw_image = payload.get("imageUrl") if "imageUrl" in payload else payload.get("image_url")
        record["imageUrl"] = validate_image_url(raw_image, "imageUrl")

    if "displayOrder" in payload or "display_order" in payload:
        raw_order = payload.get("displayOrder") if "displayOrder" in payload else payload.get("display_order")
        if raw_order is None or raw_order == "":
            record["displayOrder"] = None
        else:
            record["displayOrder"] = validate_positive_int_field(raw_order, "displayOrder")

    if "mediaLinks" in payload or "media_links" in payload:
        raw_links = payload.get("mediaLinks") if "mediaLinks" in payload else payload.get("media_links")
        if raw_links is None:
            media_links = []
        elif not isinstance(raw_links, list):
            raise CMSValidationError(
                "Field 'mediaLinks' must be a list.",
                status_code=400,
                code="VALIDATION_ERROR",
                field="mediaLinks",
            )
        else:
            media_links = [_parse_media_link_entry(item) for item in raw_links]

    if partial and not record and media_links is None:
        raise CMSValidationError(
            "At least one updatable field must be provided.",
            status_code=400,
            code="EMPTY_UPDATE",
        )

    return record, media_links


def _parse_media_link_payload(
    payload: dict,
    *,
    partial: bool = False,
    forced_post_id: int | None = None,
    existing: dict | None = None,
) -> dict:
    """Validate and sanitize a standalone or post-scoped media link payload."""
    record: dict = {}

    if forced_post_id is not None:
        record["postId"] = forced_post_id
    elif "postId" in payload or "post_id" in payload:
        raw_post_id = payload.get("postId") if "postId" in payload else payload.get("post_id")
        if raw_post_id is None:
            record["postId"] = None
        else:
            record["postId"] = validate_positive_int_field(raw_post_id, "postId")
    elif not partial:
        record["postId"] = None

    if "title" in payload:
        record["title"] = sanitize_plain_text(
            payload.get("title"), "title", required=False, max_length=160
        )
    elif not partial:
        record["title"] = ""

    has_url = any(
        k in payload
        for k in (
            "url",
            "originalUrl",
            "original_url",
            "canonicalUrl",
            "canonical_url",
            "embedUrl",
            "embed_url",
        )
    )
    has_type = "mediaType" in payload or "media_type" in payload
    if not partial or has_url or has_type:
        if has_url:
            raw_url = (
                payload.get("url")
                or payload.get("originalUrl")
                or payload.get("original_url")
                or payload.get("canonicalUrl")
                or payload.get("canonical_url")
                or payload.get("embedUrl")
                or payload.get("embed_url")
                or ""
            )
        elif existing is not None:
            raw_url = existing.get("originalUrl") or existing.get("canonicalUrl") or existing.get("embedUrl") or ""
        else:
            raw_url = ""

        if not raw_url:
            raise CMSValidationError(
                "Field 'url' is required.",
                status_code=400,
                code="MISSING_MEDIA_URL",
                field="url",
            )

        requested_type = (
            payload.get("mediaType")
            if "mediaType" in payload
            else payload.get("media_type")
        )
        normalized = validate_external_media_url(
            raw_url,
            media_type=requested_type,
            resolve_redirects=_should_resolve_short_media_urls(),
        )
        record.update(normalized)

    if partial and not record:
        raise CMSValidationError(
            "At least one updatable field must be provided.",
            status_code=400,
            code="EMPTY_UPDATE",
        )

    return record


def _parse_form_payload(payload: dict, partial: bool = False) -> dict:
    """Validate and sanitize a Google Forms embed configuration payload."""
    record: dict = {}

    if not partial or "formType" in payload or "form_type" in payload:
        raw_type = payload.get("formType") if "formType" in payload else payload.get("form_type")
        form_type = (raw_type if isinstance(raw_type, str) else "").strip()
        if form_type not in ALLOWED_FORM_TYPES:
            safe_type = sanitize_error_value(raw_type)
            raise CMSValidationError(
                f"Invalid formType '{safe_type}'. Allowed: {', '.join(ALLOWED_FORM_TYPES)}.",
                status_code=400,
                code="INVALID_FORM_TYPE",
                field="formType",
            )
        record["formType"] = form_type

    if not partial or "title" in payload:
        record["title"] = sanitize_plain_text(
            payload.get("title"), "title", required=True, min_length=2, max_length=200
        )

    if not partial or "description" in payload:
        record["description"] = sanitize_plain_text(
            payload.get("description"),
            "description",
            required=False,
            max_length=500,
            allow_newlines=True,
        )

    has_url = any(k in payload for k in ("embedUrl", "embed_url", "url"))
    if not partial or has_url:
        raw_url = (
            payload.get("embedUrl")
            if "embedUrl" in payload
            else (payload.get("embed_url") if "embed_url" in payload else payload.get("url"))
        )
        validated_url = validate_google_forms_url(raw_url, field_name="embedUrl")
        record.update(validated_url)

    if "active" in payload:
        record["active"] = validate_bool_field(payload.get("active"), "active")
    elif not partial:
        record["active"] = True

    if "displayOrder" in payload or "display_order" in payload:
        raw_order = payload.get("displayOrder") if "displayOrder" in payload else payload.get("display_order")
        if raw_order is None:
            record["displayOrder"] = None
        else:
            record["displayOrder"] = validate_positive_int_field(raw_order, "displayOrder")
    elif not partial:
        record["displayOrder"] = None

    if partial and not record:
        raise CMSValidationError(
            "At least one updatable field must be provided.",
            status_code=400,
            code="EMPTY_UPDATE",
        )

    return record


def _validate_reorder_ids(
    payload: dict, camel_key: str, snake_key: str, item_label: str
) -> list[int]:
    """Validate and deduplicate a non-empty list of positive entity IDs for reordering."""
    raw_ids = payload.get(camel_key) if camel_key in payload else payload.get(snake_key)
    if not isinstance(raw_ids, list) or len(raw_ids) == 0:
        raise CMSValidationError(
            f"Field '{camel_key}' must be a non-empty list of {item_label} IDs.",
            status_code=400,
            code="VALIDATION_ERROR",
            field=camel_key,
        )
    validated_ids: list[int] = []
    seen_ids: set[int] = set()
    for item in raw_ids:
        entity_id = validate_positive_int_field(item, camel_key)
        if entity_id in seen_ids:
            raise CMSValidationError(
                f"Field '{camel_key}' must not contain duplicate IDs.",
                status_code=400,
                code="VALIDATION_ERROR",
                field=camel_key,
            )
        seen_ids.add(entity_id)
        validated_ids.append(entity_id)
    return validated_ids


def _load_dotenv_defaults() -> dict[str, str]:
    """Read key-value defaults from project or backend .env files without mutating os.environ."""
    values: dict[str, str] = {}
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(backend_dir)
    for env_path in (
        os.path.join(project_root, ".env"),
        os.path.join(backend_dir, ".env"),
    ):
        if not os.path.isfile(env_path):
            continue
        with open(env_path, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                if key and key not in values:
                    values[key] = value
    return values


def create_app(test_config=None):
    """Application factory for creating and configuring the Flask app."""
    is_testing = bool(test_config and test_config.get("TESTING"))
    dotenv_values = {} if is_testing else _load_dotenv_defaults()

    def _get_setting(key: str, default: str = "") -> str:
        if key in os.environ:
            return os.environ[key]
        return dotenv_values.get(key, default)

    raw_env = (
        (test_config.get("MAHJAR_ENV") if test_config and "MAHJAR_ENV" in test_config else None)
        or _get_setting("MAHJAR_ENV")
        or _get_setting("FLASK_ENV")
        or "development"
    )
    mahjar_env = str(raw_env).strip().lower()
    is_production = mahjar_env == "production" and not is_testing

    secret_from_env = _get_setting("MAHJAR_SECRET_KEY") or _get_setting("SECRET_KEY")
    default_secret_key = secret_from_env if is_production else (secret_from_env or secrets.token_hex(32))
    fallback_keys = parse_csv_list(_get_setting("MAHJAR_SECRET_KEY_FALLBACKS"))

    raw_cors_env = _get_setting("MAHJAR_CORS_ALLOWED_ORIGINS")
    if raw_cors_env:
        default_cors_origins = raw_cors_env
    elif is_production:
        default_cors_origins = ()
    else:
        default_cors_origins = DEFAULT_DEV_CORS_ORIGINS

    raw_exempt_paths = _get_setting("MAHJAR_HTTPS_EXEMPT_PATHS")
    exempt_https_paths = (
        tuple(parse_csv_list(raw_exempt_paths))
        if raw_exempt_paths
        else DEFAULT_HTTPS_EXEMPT_PATHS
    )

    backend_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(backend_dir)

    data_dir = (
        (test_config.get("DATA_DIR") if test_config and "DATA_DIR" in test_config else None)
        or _get_setting("MAHJAR_DATA_DIR")
    ).strip()

    storage_backend = (
        (test_config.get("STORAGE_BACKEND") if test_config and "STORAGE_BACKEND" in test_config else None)
        or _get_setting("MAHJAR_STORAGE_BACKEND")
        or "auto"
    ).strip().lower()

    database_url = (
        (test_config.get("DATABASE_URL") if test_config and "DATABASE_URL" in test_config else None)
        or _get_setting("MAHJAR_DATABASE_URL")
    ).strip()

    default_upload_dir = (
        _get_setting("MAHJAR_MEDIA_UPLOAD_DIR")
        or (os.path.join(data_dir, "uploads", "images") if data_dir else "")
        or os.path.join(backend_dir, "uploads", "images")
    )

    default_frontend_dist = (
        _get_setting("MAHJAR_FRONTEND_DIST_DIR")
        or os.path.join(project_root, "frontend", "dist")
    )

    flask_app = Flask(__name__)
    flask_app.config.update({
        "MAHJAR_ENV": mahjar_env,
        "DATA_DIR": data_dir,
        "STORAGE_BACKEND": storage_backend,
        "DATABASE_URL": database_url,
        "SECRET_KEY": default_secret_key,
        "SECRET_KEY_FALLBACKS": fallback_keys,
        "ADMIN_USERNAME": _get_setting("MAHJAR_ADMIN_USERNAME", "admin"),
        "ADMIN_PASSWORD_HASH": _get_setting("MAHJAR_ADMIN_PASSWORD_HASH", ""),
        "ADMIN_PASSWORD": _get_setting("MAHJAR_ADMIN_PASSWORD", ""),
        "ADMIN_TOKEN_TTL_SECONDS": parse_int(
            _get_setting("MAHJAR_ADMIN_TOKEN_TTL_SECONDS"),
            DEFAULT_ADMIN_TOKEN_TTL_SECONDS,
            min_value=1,
        ),
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": _get_setting("MAHJAR_COOKIE_SAMESITE", "Lax"),
        "SESSION_COOKIE_SECURE": parse_bool(
            _get_setting("MAHJAR_COOKIE_SECURE"), default=is_production
        ),
        "ENFORCE_HTTPS": parse_bool(
            _get_setting("MAHJAR_ENFORCE_HTTPS"), default=is_production
        ),
        "HTTPS_EXEMPT_PATHS": exempt_https_paths,
        "TRUST_PROXY_COUNT": parse_int(
            _get_setting("MAHJAR_TRUST_PROXY_COUNT"),
            1 if is_production else 0,
            min_value=0,
        ),
        "HSTS_MAX_AGE": parse_int(
            _get_setting("MAHJAR_HSTS_MAX_AGE"), 31536000, min_value=0
        ),
        "HSTS_PRELOAD": parse_bool(_get_setting("MAHJAR_HSTS_PRELOAD"), default=False),
        "CORS_ALLOWED_ORIGINS": default_cors_origins,
        "CORS_ALLOW_DEV_LAN_ORIGINS": parse_bool(
            _get_setting("MAHJAR_CORS_ALLOW_DEV_LAN_ORIGINS"),
            default=(not is_production and not is_testing and not bool(raw_cors_env)),
        ),
        "CORS_ALLOW_INSECURE_ORIGINS": parse_bool(
            _get_setting("MAHJAR_CORS_ALLOW_INSECURE_ORIGINS"), default=False
        ),
        "CORS_ALLOWED_METHODS": DEFAULT_CORS_ALLOWED_METHODS,
        "CORS_ALLOWED_HEADERS": DEFAULT_CORS_ALLOWED_HEADERS,
        "CORS_EXPOSED_HEADERS": DEFAULT_CORS_EXPOSED_HEADERS,
        "CORS_MAX_AGE": parse_int(_get_setting("MAHJAR_CORS_MAX_AGE"), 600, min_value=0),
        "RATE_LIMIT_ENABLED": parse_bool(
            _get_setting("MAHJAR_RATE_LIMIT_ENABLED"), default=True
        ),
        "RATE_LIMIT_AUTH_REQUESTS": parse_int(
            _get_setting("MAHJAR_RATE_LIMIT_AUTH_REQUESTS"), 10, min_value=1
        ),
        "RATE_LIMIT_AUTH_WINDOW_SECONDS": parse_int(
            _get_setting("MAHJAR_RATE_LIMIT_AUTH_WINDOW_SECONDS"), 60, min_value=1
        ),
        "RATE_LIMIT_WRITE_REQUESTS": parse_int(
            _get_setting("MAHJAR_RATE_LIMIT_WRITE_REQUESTS"), 60, min_value=1
        ),
        "RATE_LIMIT_WRITE_WINDOW_SECONDS": parse_int(
            _get_setting("MAHJAR_RATE_LIMIT_WRITE_WINDOW_SECONDS"), 60, min_value=1
        ),
        "RATE_LIMIT_UPLOAD_REQUESTS": parse_int(
            _get_setting("MAHJAR_RATE_LIMIT_UPLOAD_REQUESTS"), 20, min_value=1
        ),
        "RATE_LIMIT_UPLOAD_WINDOW_SECONDS": parse_int(
            _get_setting("MAHJAR_RATE_LIMIT_UPLOAD_WINDOW_SECONDS"), 60, min_value=1
        ),
        "RATE_LIMIT_PUBLIC_WRITE_REQUESTS": parse_int(
            _get_setting("MAHJAR_RATE_LIMIT_PUBLIC_WRITE_REQUESTS"), 30, min_value=1
        ),
        "RATE_LIMIT_PUBLIC_WRITE_WINDOW_SECONDS": parse_int(
            _get_setting("MAHJAR_RATE_LIMIT_PUBLIC_WRITE_WINDOW_SECONDS"), 60, min_value=1
        ),
        "RATE_LIMIT_MAX_KEYS": parse_int(
            _get_setting("MAHJAR_RATE_LIMIT_MAX_KEYS"), 10000, min_value=1
        ),
        "MAX_CONTENT_LENGTH": parse_int(
            _get_setting("MAHJAR_MAX_CONTENT_LENGTH"), 6 * 1024 * 1024, min_value=1024
        ),
        "MAX_JSON_BODY_BYTES": parse_int(
            _get_setting("MAHJAR_MAX_JSON_BODY_BYTES"), 64 * 1024, min_value=64
        ),
        "MAX_JSON_DEPTH": parse_int(
            _get_setting("MAHJAR_MAX_JSON_DEPTH"), 8, min_value=1
        ),
        "MAX_QUERY_PARAM_LENGTH": parse_int(
            _get_setting("MAHJAR_MAX_QUERY_PARAM_LENGTH"), 2048, min_value=1
        ),
        "REQUIRE_AUTH_FOR_MEDIA_UPLOAD": parse_bool(
            _get_setting("MAHJAR_REQUIRE_AUTH_FOR_MEDIA_UPLOAD"), default=is_production
        ),
        "MEDIA_UPLOAD_DIR": default_upload_dir,
        "MAX_IMAGE_UPLOAD_BYTES": MAX_IMAGE_UPLOAD_BYTES,
        "MAX_MEDIA_STORAGE_BYTES": parse_int(
            _get_setting("MAHJAR_MAX_MEDIA_STORAGE_BYTES"),
            DEFAULT_MAX_MEDIA_STORAGE_BYTES,
            min_value=1024,
        ),
        "IMAGE_MAX_WIDTH": MAX_IMAGE_WIDTH,
        "IMAGE_MAX_HEIGHT": MAX_IMAGE_HEIGHT,
        "IMAGE_DEFAULT_FORMAT": DEFAULT_OUTPUT_FORMAT,
        "SERVE_FRONTEND_DIST": parse_bool(
            _get_setting("MAHJAR_SERVE_FRONTEND"), default=False
        ),
        "FRONTEND_DIST_DIR": default_frontend_dist,
    })

    if test_config:
        flask_app.config.update(test_config)

    configure_platform_security(flask_app)

    if "CMS_DATA_FILE" in flask_app.config:
        cms_data_file = flask_app.config["CMS_DATA_FILE"]
    elif _get_setting("MAHJAR_CMS_DATA_FILE"):
        cms_data_file = _get_setting("MAHJAR_CMS_DATA_FILE")
    elif flask_app.config.get("DATA_DIR"):
        default_filename = (
            "cms_data.sqlite3"
            if flask_app.config.get("STORAGE_BACKEND") == "sqlite"
            else "cms_data.json"
        )
        cms_data_file = os.path.join(flask_app.config["DATA_DIR"], default_filename)
    elif not flask_app.config.get("TESTING"):
        default_filename = (
            "cms_data.sqlite3"
            if flask_app.config.get("STORAGE_BACKEND") == "sqlite"
            else "cms_data.json"
        )
        cms_data_file = os.path.join(backend_dir, "instance", default_filename)
    else:
        cms_data_file = None

    flask_app.extensions["cms_store"] = create_cms_store(
        DEFAULT_COMMITTEE_MEMBERS,
        DEFAULT_POSTS,
        DEFAULT_GOOGLE_FORMS,
        data_file=cms_data_file,
        storage_backend=flask_app.config["STORAGE_BACKEND"],
        database_url=flask_app.config["DATABASE_URL"] or None,
    )
    flask_app.extensions["revoked_admin_ids"] = set()

    def _get_store() -> CMSStore:
        return current_app.extensions["cms_store"]

    def require_admin_auth(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            g.admin_auth = authenticate_admin_request(current_app, request, session)
            return view_func(*args, **kwargs)

        return wrapper

    @flask_app.errorhandler(CMSValidationError)
    def handle_cms_validation_error(exc: CMSValidationError):
        body = {"error": str(exc), "code": exc.code}
        if exc.field:
            body["field"] = exc.field
        return jsonify(body), exc.status_code

    @flask_app.errorhandler(MediaValidationError)
    def handle_media_validation_error(exc: MediaValidationError):
        return jsonify({"error": str(exc), "code": exc.code}), exc.status_code

    @flask_app.errorhandler(AdminAuthError)
    def handle_admin_auth_error(exc: AdminAuthError):
        response = jsonify({"error": str(exc), "code": exc.code})
        response.status_code = exc.status_code
        if exc.status_code == 401:
            response.headers["WWW-Authenticate"] = "Bearer"
        return response

    @flask_app.errorhandler(413)
    def handle_request_entity_too_large(_error):
        return (
            jsonify({
                "error": "Uploaded image exceeds the maximum allowed size.",
                "code": "FILE_TOO_LARGE",
            }),
            413,
        )

    @flask_app.route("/api/health", methods=["GET"])
    def health_check():
        return jsonify({
            "status": "ok",
            "service": "MahjarParents Backend API",
        })

    @flask_app.route("/api/ready", methods=["GET"])
    def readiness_check():
        store = _get_store()
        storage_diag = (
            store.storage_info()
            if hasattr(store, "storage_info")
            else {"backend": "json", "persisted": False, "sizeBytes": 0, "counts": {}}
        )
        media_stats = inspect_media_storage(flask_app.config["MEDIA_UPLOAD_DIR"])
        dist_dir = os.path.abspath(flask_app.config["FRONTEND_DIST_DIR"])
        dist_ready = bool(
            flask_app.config.get("SERVE_FRONTEND_DIST")
            and os.path.isfile(os.path.join(dist_dir, "index.html"))
        )
        resp = jsonify({
            "status": "ready",
            "service": "MahjarParents Backend API",
            "storage": storage_diag,
            "media": {
                "assetCount": media_stats["assetCount"],
                "usedBytes": media_stats["usedBytes"],
                "maxStorageBytes": int(flask_app.config["MAX_MEDIA_STORAGE_BYTES"]),
                "disallowedFiles": media_stats["disallowedFiles"],
                "rawAvStorageAllowed": False,
            },
            "frontend": {
                "servedByFlask": dist_ready,
            },
        })
        resp.headers["Cache-Control"] = "no-store"
        return resp, 200

    @flask_app.route("/api/committee", methods=["GET"])
    def get_committee():
        payload_bytes, etag = _get_cached_committee_response()
        return _build_cached_json_response(
            payload_bytes, etag, COMMITTEE_CACHE_TTL_SECONDS
        )

    @flask_app.route("/api/posts", methods=["GET"])
    def get_posts():
        category = (request.args.get("category") or "").strip()
        if category and category != "all" and category not in ALLOWED_POST_CATEGORIES:
            safe_category = sanitize_error_value(category)
            return (
                jsonify(
                    {
                        "error": f"Invalid category '{safe_category}'.",
                        "allowedCategories": ["all", *ALLOWED_POST_CATEGORIES],
                    }
                ),
                400,
            )

        limit_val, limit_err = _parse_positive_int(
            request.args.get("limit"), "limit", allow_zero=False
        )
        if limit_err:
            return jsonify({"error": limit_err}), 400

        offset_val, offset_err = _parse_positive_int(
            request.args.get("offset"), "offset", allow_zero=True
        )
        if offset_err:
            return jsonify({"error": offset_err}), 400

        page_val, page_err = _parse_positive_int(
            request.args.get("page"), "page", allow_zero=False
        )
        if page_err:
            return jsonify({"error": page_err}), 400

        per_page_raw = request.args.get("per_page") or request.args.get("perPage")
        per_page_val, per_page_err = _parse_positive_int(
            per_page_raw, "per_page", allow_zero=False
        )
        if per_page_err:
            return jsonify({"error": per_page_err}), 400

        envelope_flag = (request.args.get("envelope") or "").strip().lower() in (
            "1",
            "true",
            "yes",
        )

        ordered_posts, generation = _get_cached_ordered_posts_with_generation()

        effective_limit = limit_val or per_page_val
        if effective_limit is not None:
            effective_limit = min(effective_limit, MAX_POSTS_LIMIT)

        if offset_val is not None:
            effective_offset = offset_val
        elif page_val is not None:
            step = effective_limit or len(ordered_posts) or 10
            effective_offset = (page_val - 1) * step
            if effective_limit is None:
                effective_limit = step
        else:
            effective_offset = 0

        cache_key = (
            category or "all",
            effective_limit,
            effective_offset,
            page_val,
            envelope_flag,
        )
        with _posts_cache_lock:
            cached_entry = (
                _posts_cache["responses"].get(cache_key)
                if _posts_cache["generation"] == generation
                else None
            )

        if cached_entry is not None:
            payload_bytes, etag, total_count, has_more = cached_entry
        else:
            if not category or category == "all":
                filtered = ordered_posts
            else:
                filtered = [
                    post for post in ordered_posts if post["category"] == category
                ]

            total_count = len(filtered)
            if effective_limit is not None:
                sliced = filtered[effective_offset : effective_offset + effective_limit]
                has_more = (effective_offset + effective_limit) < total_count
                per_page_num = effective_limit
            else:
                sliced = filtered[effective_offset:] if effective_offset else filtered
                has_more = False
                per_page_num = total_count or 1

            current_page = (
                page_val
                if page_val is not None
                else ((effective_offset // per_page_num) + 1 if per_page_num else 1)
            )
            total_pages = (
                math.ceil(total_count / per_page_num)
                if total_count > 0 and per_page_num > 0
                else 1
            )

            if envelope_flag:
                response_data = {
                    "items": sliced,
                    "pagination": {
                        "total": total_count,
                        "limit": effective_limit or total_count,
                        "offset": effective_offset,
                        "page": current_page,
                        "perPage": effective_limit or total_count,
                        "totalPages": total_pages,
                        "hasMore": has_more,
                    },
                }
            else:
                response_data = sliced

            payload_bytes, etag = _serialize_json_and_etag(response_data)
            with _posts_cache_lock:
                if _posts_cache["generation"] == generation:
                    _cache_bounded_response(
                        _posts_cache["responses"],
                        cache_key,
                        (payload_bytes, etag, total_count, has_more),
                    )

        return _build_cached_json_response(
            payload_bytes,
            etag,
            POSTS_CACHE_TTL_SECONDS,
            extra_headers={
                "X-Total-Count": str(total_count),
                "X-Has-More": "true" if has_more else "false",
            },
        )

    @flask_app.route("/api/forms", methods=["GET"])
    def get_public_forms():
        raw_type = (
            request.args.get("type")
            or request.args.get("formType")
            or request.args.get("form_type")
            or ""
        )
        form_type = raw_type.strip()
        if form_type and form_type != "all" and form_type not in ALLOWED_FORM_TYPES:
            safe_type = sanitize_error_value(form_type)
            return (
                jsonify({
                    "error": f"Invalid form type '{safe_type}'.",
                    "code": "INVALID_FORM_TYPE",
                    "allowedFormTypes": ["all", *ALLOWED_FORM_TYPES],
                }),
                400,
            )

        envelope_flag = (request.args.get("envelope") or "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        return _build_public_forms_response(form_type, envelope_flag)

    @flask_app.route("/api/forms/validate", methods=["POST"])
    def validate_public_google_form():
        payload = _require_json_object()
        raw_url = (
            payload.get("url")
            if "url" in payload
            else (
                payload.get("embedUrl")
                if "embedUrl" in payload
                else payload.get("embed_url")
            )
        )
        validated = validate_google_forms_url(raw_url, field_name="url")
        trusted_domain = urlsplit(validated["canonicalUrl"]).hostname or TRUSTED_GOOGLE_FORMS_DOMAINS[0]
        return (
            jsonify({
                "valid": True,
                "provider": validated["provider"],
                "trustedDomain": trusted_domain,
                "formId": validated["formId"],
                "form_id": validated["formId"],
                "canonicalUrl": validated["canonicalUrl"],
                "canonical_url": validated["canonicalUrl"],
                "directUrl": validated["canonicalUrl"],
                "direct_url": validated["canonicalUrl"],
                "embedUrl": validated["embedUrl"],
                "embed_url": validated["embedUrl"],
            }),
            200,
        )

    @flask_app.route("/api/forms/<form_type>", methods=["GET"])
    def get_public_forms_by_type(form_type: str):
        cleaned_type = (form_type or "").strip()
        if cleaned_type not in ALLOWED_FORM_TYPES:
            safe_type = sanitize_error_value(cleaned_type)
            return (
                jsonify({
                    "error": f"Invalid form type '{safe_type}'.",
                    "code": "INVALID_FORM_TYPE",
                    "allowedFormTypes": list(ALLOWED_FORM_TYPES),
                }),
                400,
            )

        envelope_flag = (request.args.get("envelope") or "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        return _build_public_forms_response(cleaned_type, envelope_flag)

    @flask_app.route("/api/media/images", methods=["POST"])
    def upload_optimized_image():
        if current_app.config.get("REQUIRE_AUTH_FOR_MEDIA_UPLOAD"):
            g.admin_auth = authenticate_admin_request(current_app, request, session)
        uploaded_file = request.files.get("file") or request.files.get("image")
        if uploaded_file is None:
            return (
                jsonify({
                    "error": "Image file is required in form field 'file'.",
                    "code": "MISSING_FILE",
                }),
                400,
            )

        output_format = (
            request.form.get("format")
            or request.args.get("format")
            or flask_app.config["IMAGE_DEFAULT_FORMAT"]
        )

        configured_max_w = int(flask_app.config["IMAGE_MAX_WIDTH"])
        configured_max_h = int(flask_app.config["IMAGE_MAX_HEIGHT"])

        max_w_raw = (
            request.form.get("max_width")
            or request.form.get("maxWidth")
            or request.args.get("max_width")
            or request.args.get("maxWidth")
        )
        max_w_val, max_w_err = _parse_positive_int(max_w_raw, "max_width", allow_zero=False)
        if max_w_err:
            return jsonify({"error": max_w_err, "code": "INVALID_DIMENSIONS"}), 400
        effective_max_w = min(max_w_val, configured_max_w) if max_w_val else configured_max_w

        max_h_raw = (
            request.form.get("max_height")
            or request.form.get("maxHeight")
            or request.args.get("max_height")
            or request.args.get("maxHeight")
        )
        max_h_val, max_h_err = _parse_positive_int(max_h_raw, "max_height", allow_zero=False)
        if max_h_err:
            return jsonify({"error": max_h_err, "code": "INVALID_DIMENSIONS"}), 400
        effective_max_h = min(max_h_val, configured_max_h) if max_h_val else configured_max_h

        quality_raw = request.form.get("quality") or request.args.get("quality")
        file_bytes = uploaded_file.read()

        try:
            result = optimize_image(
                file_bytes,
                filename=uploaded_file.filename or "",
                content_type=uploaded_file.content_type or "",
                output_format=output_format,
                max_width=effective_max_w,
                max_height=effective_max_h,
                quality=quality_raw,
                max_bytes=int(flask_app.config["MAX_IMAGE_UPLOAD_BYTES"]),
            )
            save_optimized_image(
                result,
                flask_app.config["MEDIA_UPLOAD_DIR"],
                max_storage_bytes=int(flask_app.config["MAX_MEDIA_STORAGE_BYTES"]),
            )
        except MediaValidationError as exc:
            return jsonify({"error": str(exc), "code": exc.code}), exc.status_code

        response_payload = {
            key: value for key, value in result.items() if key != "data"
        }
        response_payload["url"] = f"/api/media/images/{result['filename']}"
        return jsonify(response_payload), 201

    @flask_app.route("/api/media/images/<filename>", methods=["GET"])
    def serve_optimized_image(filename: str):
        if not SAFE_ASSET_FILENAME_RE.match(filename):
            return (
                jsonify({
                    "error": "Invalid image filename.",
                    "code": "INVALID_FILENAME",
                }),
                400,
            )

        upload_dir = os.path.abspath(flask_app.config["MEDIA_UPLOAD_DIR"])
        cache_key = (upload_dir, filename)
        mimetype = "image/webp" if filename.endswith(".webp") else "image/jpeg"

        with _media_asset_cache_lock:
            cached_bytes = _media_asset_cache.get(cache_key)

        if cached_bytes is not None:
            return Response(
                response=cached_bytes,
                status=200,
                mimetype=mimetype,
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable",
                    "X-Content-Type-Options": "nosniff",
                },
            )

        asset_path = os.path.join(upload_dir, filename)
        if not os.path.isfile(asset_path):
            return (
                jsonify({
                    "error": "Optimized image asset not found.",
                    "code": "ASSET_NOT_FOUND",
                }),
                404,
            )

        file_size = os.path.getsize(asset_path)
        if file_size <= MAX_CACHED_MEDIA_ASSET_BYTES:
            with open(asset_path, "rb") as asset_fh:
                asset_bytes = asset_fh.read()
            with _media_asset_cache_lock:
                if (
                    cache_key not in _media_asset_cache
                    and len(_media_asset_cache) >= MAX_CACHED_MEDIA_ASSETS
                ):
                    oldest_key = next(iter(_media_asset_cache))
                    _media_asset_cache.pop(oldest_key, None)
                _media_asset_cache[cache_key] = asset_bytes
            return Response(
                response=asset_bytes,
                status=200,
                mimetype=mimetype,
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable",
                    "X-Content-Type-Options": "nosniff",
                },
            )

        response = send_from_directory(upload_dir, filename, mimetype=mimetype)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @flask_app.route("/api/media/external", methods=["POST"])
    def validate_external_media():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not payload.get("url"):
            return (
                jsonify({
                    "error": "Field 'url' is required.",
                    "code": "MISSING_MEDIA_URL",
                }),
                400,
            )

        try:
            normalized = validate_external_media_url(
                payload.get("url"),
                media_type=payload.get("mediaType") or payload.get("media_type"),
                resolve_redirects=_should_resolve_short_media_urls(),
            )
        except MediaValidationError as exc:
            return jsonify({"error": str(exc), "code": exc.code}), exc.status_code

        return jsonify(normalized), 200

    # --- Protected Admin CMS Auth & CRUD Routes ---

    @flask_app.route("/api/admin/auth/login", methods=["POST"])
    def admin_login():
        payload = _require_json_object()
        username = verify_admin_credentials(
            current_app.config,
            payload.get("username"),
            payload.get("password"),
        )
        ttl_seconds = int(
            current_app.config.get(
                "ADMIN_TOKEN_TTL_SECONDS", DEFAULT_ADMIN_TOKEN_TTL_SECONDS
            )
        )
        token, _jti = issue_admin_token(str(current_app.config["SECRET_KEY"]), username)

        session_id = secrets.token_urlsafe(16)
        session.clear()
        session["admin_authenticated"] = True
        session["admin_username"] = username
        session["admin_session_id"] = session_id
        session["admin_issued_at"] = time.time()

        return (
            jsonify({
                "authenticated": True,
                "username": username,
                "token": token,
                "tokenType": "Bearer",
                "expiresIn": ttl_seconds,
            }),
            200,
        )

    @flask_app.route("/api/admin/auth/logout", methods=["POST"])
    @require_admin_auth
    def admin_logout():
        revoked_ids: set[str] = current_app.extensions.setdefault(
            "revoked_admin_ids", set()
        )
        if g.admin_auth.get("jti"):
            revoked_ids.add(g.admin_auth["jti"])
        if g.admin_auth.get("sessionId"):
            revoked_ids.add(g.admin_auth["sessionId"])
        session.clear()
        return jsonify({"authenticated": False, "loggedOut": True}), 200

    @flask_app.route("/api/admin/auth/me", methods=["GET"])
    @require_admin_auth
    def admin_me():
        return (
            jsonify({
                "authenticated": True,
                "username": g.admin_auth["username"],
                "authMethod": g.admin_auth["authMethod"],
            }),
            200,
        )

    # --- Committee Members CRUD ---

    @flask_app.route("/api/admin/committee", methods=["GET"])
    @require_admin_auth
    def admin_list_committee():
        ordered = _normalize_and_order_committee_members(_get_store().list_committee())
        return jsonify(ordered), 200

    @flask_app.route("/api/admin/committee", methods=["POST"])
    @require_admin_auth
    def admin_create_committee():
        payload = _require_json_object()
        record = _parse_committee_payload(payload, partial=False)
        created = _get_store().create_committee_member(record)
        clear_committee_cache()
        return jsonify(_format_committee_record(created)), 201

    @flask_app.route("/api/admin/committee/<int:member_id>", methods=["PUT"])
    @require_admin_auth
    def admin_update_committee(member_id: int):
        payload = _require_json_object()
        updates = _parse_committee_payload(payload, partial=True)
        updated = _get_store().update_committee_member(member_id, updates)
        if updated is None:
            return (
                jsonify({
                    "error": f"Committee member {member_id} not found.",
                    "code": "NOT_FOUND",
                }),
                404,
            )
        clear_committee_cache()
        return jsonify(_format_committee_record(updated)), 200

    @flask_app.route("/api/admin/committee/<int:member_id>", methods=["DELETE"])
    @require_admin_auth
    def admin_delete_committee(member_id: int):
        deleted = _get_store().delete_committee_member(member_id)
        if not deleted:
            return (
                jsonify({
                    "error": f"Committee member {member_id} not found.",
                    "code": "NOT_FOUND",
                }),
                404,
            )
        clear_committee_cache()
        return jsonify({"deleted": True, "id": member_id}), 200

    @flask_app.route("/api/admin/committee/reorder", methods=["PUT"])
    @require_admin_auth
    def admin_reorder_committee():
        payload = _require_json_object()
        validated_ids = _validate_reorder_ids(
            payload, "memberIds", "member_ids", "committee member"
        )
        reordered = _get_store().reorder_committee(validated_ids)
        if reordered is None:
            return (
                jsonify({
                    "error": "One or more committee member IDs were not found.",
                    "code": "NOT_FOUND",
                }),
                404,
            )
        clear_committee_cache()
        return jsonify(_normalize_and_order_committee_members(_get_store().list_committee())), 200

    # --- Posts CRUD ---

    @flask_app.route("/api/admin/posts", methods=["GET"])
    @require_admin_auth
    def admin_list_posts():
        ordered = _normalize_and_order_posts(_get_store().list_posts())
        return jsonify(ordered), 200

    @flask_app.route("/api/admin/posts", methods=["POST"])
    @require_admin_auth
    def admin_create_post():
        payload = _require_json_object()
        record, media_links = _parse_post_payload(payload, partial=False)
        created = _get_store().create_post(record, media_links=media_links)
        clear_posts_cache()
        return jsonify(_format_post_record(created)), 201

    @flask_app.route("/api/admin/posts/<int:post_id>", methods=["PUT"])
    @require_admin_auth
    def admin_update_post(post_id: int):
        payload = _require_json_object()
        updates, media_links = _parse_post_payload(payload, partial=True)
        updated = _get_store().update_post(post_id, updates, media_links=media_links)
        if updated is None:
            return (
                jsonify({
                    "error": f"Post {post_id} not found.",
                    "code": "NOT_FOUND",
                }),
                404,
            )
        clear_posts_cache()
        return jsonify(_format_post_record(updated)), 200

    @flask_app.route("/api/admin/posts/<int:post_id>", methods=["DELETE"])
    @require_admin_auth
    def admin_delete_post(post_id: int):
        deleted = _get_store().delete_post(post_id)
        if not deleted:
            return (
                jsonify({
                    "error": f"Post {post_id} not found.",
                    "code": "NOT_FOUND",
                }),
                404,
            )
        clear_posts_cache()
        return jsonify({"deleted": True, "id": post_id}), 200

    @flask_app.route("/api/admin/posts/reorder", methods=["PUT"])
    @require_admin_auth
    def admin_reorder_posts():
        payload = _require_json_object()
        validated_ids = _validate_reorder_ids(
            payload, "postIds", "post_ids", "post"
        )

        reordered = _get_store().reorder_posts(validated_ids)
        if reordered is None:
            return (
                jsonify({
                    "error": "One or more post IDs were not found.",
                    "code": "NOT_FOUND",
                }),
                404,
            )
        clear_posts_cache()
        return jsonify(_normalize_and_order_posts(_get_store().list_posts())), 200

    # --- Media Links CRUD (Standalone & Post-Scoped) ---

    @flask_app.route("/api/admin/media-links", methods=["GET"])
    @require_admin_auth
    def admin_list_media_links():
        post_id_raw = request.args.get("post_id") or request.args.get("postId")
        post_id_val, err = _parse_positive_int(post_id_raw, "post_id", allow_zero=False)
        if err:
            return jsonify({"error": err, "code": "INVALID_POST_ID"}), 400
        return jsonify(_get_store().list_media_links(post_id=post_id_val)), 200

    @flask_app.route("/api/admin/media-links", methods=["POST"])
    @require_admin_auth
    def admin_create_media_link():
        payload = _require_json_object()
        record = _parse_media_link_payload(payload, partial=False)
        store = _get_store()
        if record.get("postId") is not None and store.get_post(record["postId"]) is None:
            return (
                jsonify({
                    "error": f"Post {record['postId']} not found.",
                    "code": "POST_NOT_FOUND",
                }),
                404,
            )
        created = store.create_media_link(record)
        if created.get("postId") is not None:
            clear_posts_cache()
        return jsonify(created), 201

    @flask_app.route("/api/admin/media-links/<int:link_id>", methods=["PUT"])
    @require_admin_auth
    def admin_update_media_link(link_id: int):
        payload = _require_json_object()
        store = _get_store()
        existing = store.get_media_link(link_id)
        if existing is None:
            return (
                jsonify({
                    "error": f"Media link {link_id} not found.",
                    "code": "NOT_FOUND",
                }),
                404,
            )
        updates = _parse_media_link_payload(payload, partial=True, existing=existing)
        if updates.get("postId") is not None and store.get_post(updates["postId"]) is None:
            return (
                jsonify({
                    "error": f"Post {updates['postId']} not found.",
                    "code": "POST_NOT_FOUND",
                }),
                404,
            )
        updated = store.update_media_link(link_id, updates)
        clear_posts_cache()
        return jsonify(updated), 200

    @flask_app.route("/api/admin/media-links/<int:link_id>", methods=["DELETE"])
    @require_admin_auth
    def admin_delete_media_link(link_id: int):
        deleted = _get_store().delete_media_link(link_id)
        if not deleted:
            return (
                jsonify({
                    "error": f"Media link {link_id} not found.",
                    "code": "NOT_FOUND",
                }),
                404,
            )
        clear_posts_cache()
        return jsonify({"deleted": True, "id": link_id}), 200

    @flask_app.route("/api/admin/posts/<int:post_id>/media-links", methods=["POST"])
    @require_admin_auth
    def admin_create_post_media_link(post_id: int):
        store = _get_store()
        if store.get_post(post_id) is None:
            return (
                jsonify({
                    "error": f"Post {post_id} not found.",
                    "code": "POST_NOT_FOUND",
                }),
                404,
            )
        payload = _require_json_object()
        record = _parse_media_link_payload(payload, partial=False, forced_post_id=post_id)
        created = store.create_media_link(record)
        clear_posts_cache()
        return jsonify(created), 201

    @flask_app.route(
        "/api/admin/posts/<int:post_id>/media-links/<int:link_id>", methods=["PUT"]
    )
    @require_admin_auth
    def admin_update_post_media_link(post_id: int, link_id: int):
        store = _get_store()
        existing = store.get_media_link(link_id)
        if existing is None or existing.get("postId") != post_id:
            return (
                jsonify({
                    "error": f"Media link {link_id} for post {post_id} not found.",
                    "code": "NOT_FOUND",
                }),
                404,
            )
        payload = _require_json_object()
        updates = _parse_media_link_payload(
            payload, partial=True, forced_post_id=post_id, existing=existing
        )
        updated = store.update_media_link(link_id, updates)
        clear_posts_cache()
        return jsonify(updated), 200

    @flask_app.route(
        "/api/admin/posts/<int:post_id>/media-links/<int:link_id>", methods=["DELETE"]
    )
    @require_admin_auth
    def admin_delete_post_media_link(post_id: int, link_id: int):
        store = _get_store()
        existing = store.get_media_link(link_id)
        if existing is None or existing.get("postId") != post_id:
            return (
                jsonify({
                    "error": f"Media link {link_id} for post {post_id} not found.",
                    "code": "NOT_FOUND",
                }),
                404,
            )
        store.delete_media_link(link_id)
        clear_posts_cache()
        return jsonify({"deleted": True, "id": link_id, "postId": post_id}), 200

    # --- Google Forms Embed URLs CRUD ---

    @flask_app.route("/api/admin/forms", methods=["GET"])
    @require_admin_auth
    def admin_list_forms():
        forms = [_format_form_record(form) for form in _get_store().list_forms()]
        return jsonify(forms), 200

    @flask_app.route("/api/admin/forms", methods=["POST"])
    @require_admin_auth
    def admin_create_form():
        payload = _require_json_object()
        record = _parse_form_payload(payload, partial=False)
        created = _get_store().create_form(record)
        clear_forms_cache()
        return jsonify(_format_form_record(created)), 201

    @flask_app.route("/api/admin/forms/<int:form_id>", methods=["PUT"])
    @require_admin_auth
    def admin_update_form(form_id: int):
        payload = _require_json_object()
        updates = _parse_form_payload(payload, partial=True)
        updated = _get_store().update_form(form_id, updates)
        if updated is None:
            return (
                jsonify({
                    "error": f"Google Form {form_id} not found.",
                    "code": "NOT_FOUND",
                }),
                404,
            )
        clear_forms_cache()
        return jsonify(_format_form_record(updated)), 200

    @flask_app.route("/api/admin/forms/<int:form_id>", methods=["DELETE"])
    @require_admin_auth
    def admin_delete_form(form_id: int):
        deleted = _get_store().delete_form(form_id)
        if not deleted:
            return (
                jsonify({
                    "error": f"Google Form {form_id} not found.",
                    "code": "NOT_FOUND",
                }),
                404,
            )
        clear_forms_cache()
        return jsonify({"deleted": True, "id": form_id}), 200

    @flask_app.route("/api/admin/forms/reorder", methods=["PUT"])
    @require_admin_auth
    def admin_reorder_forms():
        payload = _require_json_object()
        validated_ids = _validate_reorder_ids(
            payload, "formIds", "form_ids", "Google Form"
        )
        reordered = _get_store().reorder_forms(validated_ids)
        if reordered is None:
            return (
                jsonify({
                    "error": "One or more Google Form IDs were not found.",
                    "code": "NOT_FOUND",
                }),
                404,
            )
        clear_forms_cache()
        return jsonify([_format_form_record(form) for form in _get_store().list_forms()]), 200

    if flask_app.config.get("SERVE_FRONTEND_DIST"):
        dist_root = os.path.abspath(flask_app.config["FRONTEND_DIST_DIR"])

        def _serve_spa_index():
            index_path = os.path.join(dist_root, "index.html")
            try:
                mtime_ns = os.stat(index_path).st_mtime_ns
            except OSError:
                abort(404)

            with _spa_index_cache_lock:
                cached = _spa_index_cache.get(index_path)
                if cached is not None and cached[0] == mtime_ns:
                    html_bytes = cached[1]
                else:
                    html_bytes = None

            if html_bytes is None:
                if not os.path.isfile(index_path):
                    abort(404)
                with open(index_path, "rb") as fh:
                    html_bytes = fh.read()
                with _spa_index_cache_lock:
                    _spa_index_cache[index_path] = (mtime_ns, html_bytes)

            return Response(
                response=html_bytes,
                status=200,
                mimetype="text/html",
                headers={"Cache-Control": "no-cache"},
            )

        @flask_app.route("/", methods=["GET"])
        def serve_frontend_root():
            return _serve_spa_index()

        @flask_app.route("/<path:subpath>", methods=["GET"])
        def serve_frontend_path(subpath: str):
            if subpath == "api" or subpath.startswith("api/"):
                abort(404)
            segments = [seg for seg in subpath.split("/") if seg]
            if any(seg in (".", "..") for seg in segments):
                abort(404)

            _, ext = os.path.splitext(subpath)
            if ext.lower() in RAW_AV_EXTENSIONS:
                abort(404)

            candidate = os.path.abspath(os.path.join(dist_root, subpath))
            if (
                candidate != dist_root
                and candidate.startswith(dist_root + os.sep)
                and os.path.isfile(candidate)
            ):
                resp = send_from_directory(dist_root, subpath)
                if subpath.startswith("assets/"):
                    resp.headers["Cache-Control"] = (
                        "public, max-age=31536000, immutable"
                    )
                else:
                    resp.headers["Cache-Control"] = "public, max-age=86400"
                return resp

            if ext:
                abort(404)

            return _serve_spa_index()

    return flask_app


app = create_app()


if __name__ == "__main__":
    debug_mode = parse_bool(os.environ.get("MAHJAR_DEBUG"), default=False)
    bind_host = os.environ.get("HOST", "127.0.0.1")
    bind_port = parse_int(os.environ.get("PORT"), 5000, min_value=1)
    app.run(debug=debug_mode, host=bind_host, port=bind_port)
