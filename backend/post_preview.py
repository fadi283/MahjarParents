"""Server-side HTML metadata rendering for shared announcement post previews."""

from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, quote, urlsplit

SITE_NAME = "لجنة أولياء أمور الطلاب - مدرسة المحجر الابتدائية"
DEFAULT_SITE_DESCRIPTION = (
    "المنصة الرقمية للتواصل المجتمعي – لجنة أولياء أمور الطلاب في مدرسة المحجر الابتدائية."
)
MAX_PREVIEW_DESCRIPTION_LENGTH = 200
_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = frozenset({
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtube-nocookie.com",
})

_EXISTING_HEAD_META_PATTERNS = (
    re.compile(r"<title\b[^>]*>[\s\S]*?</title>", re.IGNORECASE),
    re.compile(r"<link\b[^>]*\brel\s*=\s*(['\"])canonical\1[^>]*>", re.IGNORECASE),
    re.compile(
        r"<meta\b[^>]*\bname\s*=\s*(['\"])description\1[^>]*>",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"<meta\b[^>]*\bproperty\s*=\s*(['\"])og:(?:type|title|description|image|image:secure_url|image:type|image:width|image:height|image:alt|url)\1[^>]*>",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"<meta\b[^>]*\bproperty\s*=\s*(['\"])article:published_time\1[^>]*>",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"<meta\b[^>]*\bname\s*=\s*(['\"])twitter:(?:card|title|description|image|image:alt)\1[^>]*>",
        re.IGNORECASE | re.DOTALL,
    ),
)
_HEAD_CLOSE_RE = re.compile(r"</head>", re.IGNORECASE)
_BODY_OPEN_RE = re.compile(r"<body\b[^>]*>", re.IGNORECASE)
_UNSAFE_URL_RE = re.compile(r"[\s\x00-\x1f\x7f<>\"']")


def _normalize_origin(raw_origin: str | None) -> str:
    if not isinstance(raw_origin, str):
        return ""
    candidate = raw_origin.strip().rstrip("/")
    if not candidate or _UNSAFE_URL_RE.search(candidate):
        return ""
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        return ""
    if parsed.username or parsed.password:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc}"


def _sanitize_http_url(raw_url: str | None) -> str:
    if not isinstance(raw_url, str):
        return ""
    candidate = raw_url.strip()
    if not candidate or _UNSAFE_URL_RE.search(candidate):
        return ""
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        return ""
    if parsed.username or parsed.password:
        return ""
    return candidate


def _truncate_description(text: str, max_length: int = MAX_PREVIEW_DESCRIPTION_LENGTH) -> str:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return ""
    if len(cleaned) <= max_length:
        return cleaned
    cutoff = max_length - 1
    sliced = cleaned[:cutoff]
    last_space = sliced.rfind(" ")
    if last_space >= int(cutoff * 0.6):
        sliced = sliced[:last_space]
    return sliced.rstrip() + "…"


def _extract_youtube_video_id(raw_url: str | None) -> str:
    safe = _sanitize_http_url(raw_url)
    if not safe:
        return ""
    parsed = urlsplit(safe)
    host = (parsed.hostname or "").lower()
    if host not in _YOUTUBE_HOSTS:
        return ""

    segments = [seg for seg in parsed.path.split("/") if seg]
    video_id = ""
    if host == "youtu.be" and segments:
        video_id = segments[0]
    elif segments and segments[0] in ("shorts", "embed", "live") and len(segments) >= 2:
        video_id = segments[1]
    else:
        video_id = (parse_qs(parsed.query).get("v") or [""])[0]

    return video_id if _YOUTUBE_ID_RE.match(video_id) else ""


def _infer_image_mime_type(image_url: str) -> str:
    parsed = urlsplit(image_url)
    query_fmt = (parse_qs(parsed.query).get("format") or [""])[0].strip().lower()
    if query_fmt in ("jpeg", "jpg"):
        return "image/jpeg"
    lower_path = (parsed.path or "").lower()
    if lower_path.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower_path.endswith(".png"):
        return "image/png"
    if lower_path.endswith(".webp"):
        return "image/webp"
    if lower_path.endswith(".gif"):
        return "image/gif"
    return ""


def _format_local_media_preview_path(path: str) -> str:
    if path.startswith("/api/media/images/") and path.endswith(".webp"):
        return f"{path}?format=jpeg"
    return path


def resolve_preview_image_info(
    post: dict,
    site_origin: str,
    media_origin: str | None = None,
) -> dict:
    """Resolve preview image URL, MIME type, dimensions, and custom-image flag for a post."""
    clean_site_origin = _normalize_origin(site_origin)
    clean_media_origin = _normalize_origin(media_origin) or clean_site_origin

    candidates: list[str] = []
    youtube_video_id = ""
    if isinstance(post, dict):
        primary_img = post.get("imageUrl") or post.get("image_url") or ""
        if isinstance(primary_img, str) and primary_img.strip():
            candidates.append(primary_img.strip())

        media_links = post.get("mediaLinks") or post.get("media_links") or []
        if isinstance(media_links, list):
            for item in media_links:
                if not isinstance(item, dict):
                    continue
                m_type = str(item.get("mediaType") or item.get("media_type") or "").strip().lower()
                link_val = ""
                for key in ("canonicalUrl", "canonical_url", "embedUrl", "embed_url", "url"):
                    val = item.get(key)
                    if isinstance(val, str) and val.strip():
                        link_val = val.strip()
                        break
                if not link_val:
                    continue
                if m_type == "image":
                    candidates.append(link_val)
                elif not youtube_video_id:
                    yt_id = _extract_youtube_video_id(link_val)
                    if yt_id:
                        youtube_video_id = yt_id

    for candidate in candidates:
        if _UNSAFE_URL_RE.search(candidate):
            continue
        if candidate.startswith("/api/media/"):
            preview_path = _format_local_media_preview_path(candidate)
            resolved = f"{clean_media_origin}{preview_path}" if clean_media_origin else preview_path
            return {
                "url": resolved,
                "has_custom_image": True,
                "mime_type": _infer_image_mime_type(resolved),
                "width": None,
                "height": None,
            }
        if candidate.startswith("/") and not candidate.startswith("//"):
            resolved = f"{clean_site_origin}{candidate}" if clean_site_origin else candidate
            return {
                "url": resolved,
                "has_custom_image": True,
                "mime_type": _infer_image_mime_type(resolved),
                "width": None,
                "height": None,
            }
        safe_abs = _sanitize_http_url(candidate)
        if safe_abs:
            return {
                "url": safe_abs,
                "has_custom_image": True,
                "mime_type": _infer_image_mime_type(safe_abs),
                "width": None,
                "height": None,
            }

    if youtube_video_id:
        yt_thumb = f"https://i.ytimg.com/vi/{youtube_video_id}/hqdefault.jpg"
        return {
            "url": yt_thumb,
            "has_custom_image": True,
            "mime_type": "image/jpeg",
            "width": 480,
            "height": 360,
        }

    fallback = f"{clean_site_origin}/logo.jpg" if clean_site_origin else "/logo.jpg"
    return {
        "url": fallback,
        "has_custom_image": False,
        "mime_type": "image/jpeg",
        "width": None,
        "height": None,
    }


def resolve_preview_image_url(
    post: dict,
    site_origin: str,
    media_origin: str | None = None,
) -> tuple[str, bool]:
    """Resolve the best absolute preview image URL for a post, returning (url, has_custom_image)."""
    info = resolve_preview_image_info(post, site_origin, media_origin=media_origin)
    return info["url"], info["has_custom_image"]


def build_post_preview_html(
    template_html: str,
    post: dict,
    *,
    site_origin: str,
    media_origin: str | None = None,
) -> str:
    """Inject post-specific Open Graph, Twitter Card, and canonical tags into SPA HTML."""
    clean_site_origin = _normalize_origin(site_origin)
    post_id = str(post.get("id", "")).strip()
    encoded_id = quote(post_id, safe="")
    canonical_url = (
        f"{clean_site_origin}/posts/{encoded_id}"
        if clean_site_origin
        else f"/posts/{encoded_id}"
    )

    raw_title = " ".join(str(post.get("title") or "").split()) or SITE_NAME
    page_title = f"{raw_title} | {SITE_NAME}" if raw_title != SITE_NAME else SITE_NAME
    raw_desc = str(
        post.get("summary")
        or post.get("description")
        or post.get("content")
        or ""
    )
    description = _truncate_description(raw_desc) or DEFAULT_SITE_DESCRIPTION
    image_info = resolve_preview_image_info(
        post, clean_site_origin, media_origin=media_origin
    )
    image_url = image_info["url"]
    has_custom_image = image_info["has_custom_image"]
    twitter_card = "summary_large_image" if has_custom_image else "summary"
    published_at = str(
        post.get("publishedAt")
        or post.get("published_at")
        or post.get("createdAt")
        or post.get("created_at")
        or ""
    ).strip()

    esc = lambda value: html.escape(value, quote=True)
    meta_lines = [
        f'  <meta name="description" content="{esc(description)}" />',
        '  <meta property="og:type" content="article" />',
        f'  <meta property="og:title" content="{esc(raw_title)}" />',
        f'  <meta property="og:description" content="{esc(description)}" />',
        f'  <meta property="og:url" content="{esc(canonical_url)}" />',
        f'  <meta property="og:image" content="{esc(image_url)}" />',
    ]
    if image_url.startswith("https://"):
        meta_lines.append(
            f'  <meta property="og:image:secure_url" content="{esc(image_url)}" />'
        )
    if image_info["mime_type"]:
        meta_lines.append(
            f'  <meta property="og:image:type" content="{esc(image_info["mime_type"])}" />'
        )
    if image_info["width"] and image_info["height"]:
        meta_lines.append(
            f'  <meta property="og:image:width" content="{image_info["width"]}" />'
        )
        meta_lines.append(
            f'  <meta property="og:image:height" content="{image_info["height"]}" />'
        )
    meta_lines.append(
        f'  <meta property="og:image:alt" content="{esc(raw_title)}" />'
    )
    if published_at:
        meta_lines.append(
            f'  <meta property="article:published_time" content="{esc(published_at)}" />'
        )
    meta_lines.extend([
        f'  <meta name="twitter:card" content="{esc(twitter_card)}" />',
        f'  <meta name="twitter:title" content="{esc(raw_title)}" />',
        f'  <meta name="twitter:description" content="{esc(description)}" />',
        f'  <meta name="twitter:image" content="{esc(image_url)}" />',
        f'  <meta name="twitter:image:alt" content="{esc(raw_title)}" />',
        f'  <link rel="canonical" href="{esc(canonical_url)}" />',
        f"  <title>{esc(page_title)}</title>",
    ])
    injected_block = "\n".join(meta_lines) + "\n"

    cleaned_html = template_html
    for pattern in _EXISTING_HEAD_META_PATTERNS:
        cleaned_html = pattern.sub("", cleaned_html)
    cleaned_html = re.sub(r"\n{3,}", "\n\n", cleaned_html)

    if _HEAD_CLOSE_RE.search(cleaned_html):
        return _HEAD_CLOSE_RE.sub(lambda _m: f"{injected_block}</head>", cleaned_html, count=1)

    if _BODY_OPEN_RE.search(cleaned_html):
        return _BODY_OPEN_RE.sub(
            lambda m: f"<head>\n{injected_block}</head>{m.group(0)}",
            cleaned_html,
            count=1,
        )

    return f"<head>\n{injected_block}</head>\n{cleaned_html}"
