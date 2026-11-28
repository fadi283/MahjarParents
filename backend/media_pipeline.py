"""OpenCV image ingestion/optimization and external media URL validation utilities."""

from __future__ import annotations

import hashlib
import html
import ipaddress
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urljoin, urlsplit
import urllib.error
import urllib.request

import cv2
import numpy as np

MAX_IMAGE_UPLOAD_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_MEDIA_STORAGE_BYTES = 50 * 1024 * 1024
MAX_IMAGE_WIDTH = 1280
MAX_IMAGE_HEIGHT = 1280
MAX_IMAGE_PIXELS = 25_000_000
DEFAULT_OUTPUT_FORMAT = "webp"
SUPPORTED_OUTPUT_FORMATS = ("webp", "jpeg")
DEFAULT_WEBP_QUALITY = 80
DEFAULT_JPEG_QUALITY = 82

ALLOWED_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp"})
ALLOWED_IMAGE_MIME_TYPES = frozenset({
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/bmp",
})
RAW_AV_EXTENSIONS = frozenset({
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    ".m4v",
    ".3gp",
    ".mp3",
    ".wav",
    ".ogg",
    ".m4a",
    ".aac",
    ".flac",
    ".wma",
})

SAFE_ASSET_FILENAME_RE = re.compile(r"^[a-f0-9]{16,64}\.(webp|jpg)$")

_FORMAT_SPEC = {
    "webp": {"ext": ".webp", "mime": "image/webp", "default_quality": DEFAULT_WEBP_QUALITY},
    "jpeg": {"ext": ".jpg", "mime": "image/jpeg", "default_quality": DEFAULT_JPEG_QUALITY},
}

ALLOWED_EXTERNAL_MEDIA_TYPES = ("video", "reel", "post", "image", "audio")
EXTERNAL_IMAGE_EXTENSIONS = frozenset({
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".avif",
    ".bmp",
})

_YOUTUBE_HOSTS = frozenset({
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtube-nocookie.com",
})
_VIMEO_HOSTS = frozenset({"vimeo.com", "www.vimeo.com", "player.vimeo.com"})
_DAILYMOTION_HOSTS = frozenset({"dailymotion.com", "www.dailymotion.com", "dai.ly"})
_INSTAGRAM_HOSTS = frozenset({
    "instagram.com",
    "www.instagram.com",
    "m.instagram.com",
    "instagr.am",
    "www.instagr.am",
})
_FACEBOOK_PAGE_HOSTS = frozenset({
    "facebook.com",
    "www.facebook.com",
    "m.facebook.com",
    "web.facebook.com",
    "fb.com",
    "www.fb.com",
})
_FACEBOOK_HOSTS = frozenset({*_FACEBOOK_PAGE_HOSTS, "fb.watch"})
_TIKTOK_SHORT_HOSTS = frozenset({"vm.tiktok.com", "vt.tiktok.com"})
_TIKTOK_HOSTS = frozenset({
    "tiktok.com",
    "www.tiktok.com",
    "m.tiktok.com",
    *_TIKTOK_SHORT_HOSTS,
})
_X_HOSTS = frozenset({
    "x.com",
    "www.x.com",
    "mobile.x.com",
    "twitter.com",
    "www.twitter.com",
    "mobile.twitter.com",
})
_THREADS_HOSTS = frozenset({
    "threads.net",
    "www.threads.net",
    "threads.com",
    "www.threads.com",
})
_LINKEDIN_HOSTS = frozenset({"linkedin.com", "www.linkedin.com"})
_TELEGRAM_HOSTS = frozenset({"t.me", "telegram.me"})
_SOUNDCLOUD_PAGE_HOSTS = frozenset({"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com"})
_SOUNDCLOUD_HOSTS = frozenset({*_SOUNDCLOUD_PAGE_HOSTS, "w.soundcloud.com"})
_SPOTIFY_HOSTS = frozenset({"open.spotify.com"})
_GOOGLE_DRIVE_HOSTS = frozenset({"drive.google.com"})
_GOOGLE_PHOTOS_HOSTS = frozenset({"photos.app.goo.gl", "photos.google.com"})
_CANVA_HOSTS = frozenset({"canva.com", "www.canva.com"})

_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_VIMEO_ID_RE = re.compile(r"^\d+$")
_DRIVE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")
_DAILYMOTION_ID_RE = re.compile(r"^[A-Za-z0-9]+$")
_INSTAGRAM_SHORTCODE_RE = re.compile(r"^[A-Za-z0-9_-]{5,64}$")
_NUMERIC_ID_RE = re.compile(r"^\d+$")
_ALNUM_SLUG_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_HANDLE_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_SPOTIFY_ID_RE = re.compile(r"^[A-Za-z0-9]{10,64}$")
_CANVA_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")


class MediaValidationError(ValueError):
    """Domain validation error carrying HTTP status code and machine-readable code."""

    def __init__(self, message: str, status_code: int = 400, code: str = "INVALID_MEDIA"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _normalize_mime_type(content_type: str) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def _normalize_output_format(output_format: str) -> str:
    fmt = (output_format or DEFAULT_OUTPUT_FORMAT).strip().lower()
    if fmt == "jpg":
        fmt = "jpeg"
    if fmt not in SUPPORTED_OUTPUT_FORMATS:
        raise MediaValidationError(
            f"Unsupported output format '{output_format}'. Supported formats: webp, jpeg.",
            status_code=400,
            code="UNSUPPORTED_OUTPUT_FORMAT",
        )
    return fmt


def _validate_quality(quality: Any, default_quality: int) -> int:
    if quality is None or quality == "":
        return default_quality
    if isinstance(quality, bool):
        raise MediaValidationError(
            "Image quality must be an integer between 1 and 100.",
            status_code=400,
            code="INVALID_QUALITY",
        )
    try:
        parsed = int(quality)
    except (TypeError, ValueError) as exc:
        raise MediaValidationError(
            "Image quality must be an integer between 1 and 100.",
            status_code=400,
            code="INVALID_QUALITY",
        ) from exc
    if parsed < 1 or parsed > 100:
        raise MediaValidationError(
            "Image quality must be between 1 and 100.",
            status_code=400,
            code="INVALID_QUALITY",
        )
    return parsed


def is_raw_audio_video_upload(
    file_bytes: bytes, filename: str = "", content_type: str = ""
) -> bool:
    """Detect raw audio or video uploads via MIME type, file extension, or magic bytes."""
    mime = _normalize_mime_type(content_type)
    if mime.startswith("audio/") or mime.startswith("video/"):
        return True

    ext = Path(filename or "").suffix.lower()
    if ext in RAW_AV_EXTENSIONS:
        return True

    if not file_bytes:
        return False

    # MP4 / QuickTime / M4A container ('ftyp' box at offset 4)
    if len(file_bytes) >= 8 and file_bytes[4:8] == b"ftyp":
        return True
    # MP3 with ID3 tag or raw MPEG audio frame sync
    if file_bytes.startswith(b"ID3") or (
        len(file_bytes) >= 2 and file_bytes[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")
    ):
        return True
    # WAV (RIFF....WAVE) or AVI (RIFF....AVI )
    if (
        len(file_bytes) >= 12
        and file_bytes[:4] == b"RIFF"
        and file_bytes[8:12] in (b"WAVE", b"AVI ")
    ):
        return True
    # OGG / FLAC / Matroska-WebM (EBML)
    if file_bytes.startswith((b"OggS", b"fLaC", b"\x1a\x45\xdf\xa3")):
        return True

    return False


def _has_supported_image_magic(file_bytes: bytes) -> bool:
    """Verify magic header bytes match a supported raster image format."""
    if file_bytes.startswith(b"\xff\xd8\xff"):
        return True
    if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if len(file_bytes) >= 12 and file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
        return True
    if file_bytes.startswith(b"BM"):
        return True
    return False


def validate_image_upload(
    file_bytes: bytes,
    filename: str = "",
    content_type: str = "",
    max_bytes: int = MAX_IMAGE_UPLOAD_BYTES,
) -> None:
    """Validate uploaded image bytes, rejecting empty, oversized, raw A/V, and non-image payloads."""
    if not file_bytes:
        raise MediaValidationError(
            "Uploaded image file is empty.",
            status_code=400,
            code="EMPTY_FILE",
        )

    if len(file_bytes) > max_bytes:
        raise MediaValidationError(
            f"Image exceeds maximum allowed size of {max_bytes} bytes.",
            status_code=413,
            code="FILE_TOO_LARGE",
        )

    if is_raw_audio_video_upload(file_bytes, filename=filename, content_type=content_type):
        raise MediaValidationError(
            "Direct audio/video file uploads are not allowed; use external media links instead.",
            status_code=415,
            code="RAW_AV_NOT_ALLOWED",
        )

    mime = _normalize_mime_type(content_type)
    if mime and mime != "application/octet-stream" and mime not in ALLOWED_IMAGE_MIME_TYPES:
        raise MediaValidationError(
            f"Unsupported image MIME type '{mime}'.",
            status_code=415,
            code="UNSUPPORTED_MEDIA_TYPE",
        )

    ext = Path(filename or "").suffix.lower()
    if ext and ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise MediaValidationError(
            f"Unsupported image file extension '{ext}'.",
            status_code=415,
            code="UNSUPPORTED_MEDIA_TYPE",
        )

    if not _has_supported_image_magic(file_bytes):
        raise MediaValidationError(
            "File signature does not match a supported raster image (JPEG, PNG, WebP, BMP).",
            status_code=415,
            code="UNSUPPORTED_MEDIA_TYPE",
        )


def decode_image_bytes(file_bytes: bytes) -> np.ndarray:
    """Decode raw image bytes into a normalized uint8 OpenCV ndarray, stripping container metadata."""
    buffer = np.frombuffer(file_bytes, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_UNCHANGED)
    if image is None or image.size == 0 or image.ndim not in (2, 3):
        raise MediaValidationError(
            "Uploaded file is not a valid or decodable image.",
            status_code=400,
            code="INVALID_IMAGE_DATA",
        )

    height, width = image.shape[:2]
    if width <= 0 or height <= 0:
        raise MediaValidationError(
            "Image has invalid dimensions.",
            status_code=400,
            code="INVALID_IMAGE_DATA",
        )

    if width * height > MAX_IMAGE_PIXELS:
        raise MediaValidationError(
            f"Image pixel count ({width}x{height}) exceeds maximum limit.",
            status_code=400,
            code="IMAGE_DIMENSIONS_TOO_LARGE",
        )

    if image.dtype == np.uint16:
        return (image >> 8).astype(np.uint8)
    if image.dtype != np.uint8:
        return np.clip(image, 0, 255).astype(np.uint8)
    return image


def resize_image_if_oversized(
    image: np.ndarray,
    max_width: int = MAX_IMAGE_WIDTH,
    max_height: int = MAX_IMAGE_HEIGHT,
) -> tuple[np.ndarray, bool]:
    """Downscale oversized images while preserving aspect ratio; never upscales."""
    if max_width < 1 or max_height < 1:
        raise MediaValidationError(
            "Maximum image width and height must be positive integers.",
            status_code=400,
            code="INVALID_DIMENSIONS",
        )

    height, width = image.shape[:2]
    if width <= max_width and height <= max_height:
        return image, False

    scale = min(max_width / float(width), max_height / float(height))
    target_width = max(1, min(max_width, int(round(width * scale))))
    target_height = max(1, min(max_height, int(round(height * scale))))

    resized = cv2.resize(image, (target_width, target_height), interpolation=cv2.INTER_AREA)
    return resized, True


def _prepare_channels_for_format(image: np.ndarray, canonical_format: str) -> np.ndarray:
    """Normalize channel layout and composite alpha onto white when exporting JPEG."""
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

    channels = image.shape[2]
    if channels == 4:
        if canonical_format == "jpeg":
            alpha = image[:, :, 3:4].astype(np.float32) / 255.0
            rgb = image[:, :, :3].astype(np.float32) * alpha + 255.0 * (1.0 - alpha)
            return np.clip(rgb, 0, 255).astype(np.uint8)
        return image

    if channels == 3:
        return image

    return image[:, :, :3]


def encode_optimized_image(
    image: np.ndarray,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    quality: int | None = None,
) -> tuple[bytes, str, str]:
    """Encode an OpenCV pixel array into compressed WebP or JPEG without container metadata."""
    canonical_format = _normalize_output_format(output_format)
    spec = _FORMAT_SPEC[canonical_format]
    effective_quality = _validate_quality(quality, spec["default_quality"])

    prepared = _prepare_channels_for_format(image, canonical_format)

    if canonical_format == "webp":
        encode_params = [cv2.IMWRITE_WEBP_QUALITY, effective_quality]
    else:
        encode_params = [
            cv2.IMWRITE_JPEG_QUALITY,
            effective_quality,
            cv2.IMWRITE_JPEG_OPTIMIZE,
            1,
        ]

    ok, encoded = cv2.imencode(spec["ext"], prepared, encode_params)
    if not ok or encoded is None:
        raise MediaValidationError(
            f"Failed to encode optimized {canonical_format.upper()} image.",
            status_code=500,
            code="IMAGE_ENCODE_FAILED",
        )

    return encoded.tobytes(), canonical_format, spec["mime"]


def optimize_image(
    file_bytes: bytes,
    filename: str = "",
    content_type: str = "",
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    max_width: int = MAX_IMAGE_WIDTH,
    max_height: int = MAX_IMAGE_HEIGHT,
    quality: int | None = None,
    max_bytes: int = MAX_IMAGE_UPLOAD_BYTES,
) -> dict[str, Any]:
    """Validate, decode (stripping metadata), resize if needed, and compress an uploaded image."""
    canonical_format = _normalize_output_format(output_format)
    spec = _FORMAT_SPEC[canonical_format]
    effective_quality = _validate_quality(quality, spec["default_quality"])

    validate_image_upload(
        file_bytes,
        filename=filename,
        content_type=content_type,
        max_bytes=max_bytes,
    )

    decoded = decode_image_bytes(file_bytes)
    orig_height, orig_width = decoded.shape[:2]

    resized_img, was_resized = resize_image_if_oversized(
        decoded,
        max_width=max_width,
        max_height=max_height,
    )
    out_height, out_width = resized_img.shape[:2]

    encoded_bytes, canonical_format, mime_type = encode_optimized_image(
        resized_img,
        output_format=canonical_format,
        quality=effective_quality,
    )

    digest = hashlib.sha256(encoded_bytes).hexdigest()[:16]
    asset_filename = f"{digest}{spec['ext']}"

    return {
        "data": encoded_bytes,
        "filename": asset_filename,
        "format": canonical_format,
        "mimeType": mime_type,
        "extension": spec["ext"],
        "width": int(out_width),
        "height": int(out_height),
        "originalWidth": int(orig_width),
        "originalHeight": int(orig_height),
        "resized": was_resized,
        "originalBytes": len(file_bytes),
        "optimizedBytes": len(encoded_bytes),
        "metadataStripped": True,
    }


def transcode_image_bytes_to_jpeg(
    image_bytes: bytes,
    *,
    max_width: int = 1200,
    max_height: int = 1200,
    quality: int = DEFAULT_JPEG_QUALITY,
) -> bytes:
    """Decode stored WebP/image bytes and re-encode as JPEG for legacy social preview scrapers."""
    if not image_bytes:
        raise MediaValidationError(
            "Unable to decode stored image for JPEG preview.",
            status_code=500,
            code="IMAGE_TRANSCODE_ERROR",
        )
    try:
        decoded = decode_image_bytes(image_bytes)
    except MediaValidationError as exc:
        raise MediaValidationError(
            "Unable to decode stored image for JPEG preview.",
            status_code=500,
            code="IMAGE_TRANSCODE_ERROR",
        ) from exc

    resized_img, _ = resize_image_if_oversized(
        decoded,
        max_width=max_width,
        max_height=max_height,
    )
    jpeg_bytes, _, _ = encode_optimized_image(
        resized_img,
        output_format="jpeg",
        quality=quality,
    )
    return jpeg_bytes


def inspect_media_storage(storage_dir: str | Path) -> dict[str, Any]:
    """Inspect OpenCV-processed image asset usage and verify no raw A/V files are stored."""
    base_dir = Path(storage_dir)
    if not base_dir.is_dir():
        return {
            "assetCount": 0,
            "usedBytes": 0,
            "disallowedFiles": 0,
        }

    asset_count = 0
    used_bytes = 0
    disallowed_files = 0
    for entry in base_dir.iterdir():
        if not entry.is_file() or entry.name.startswith(".tmp_"):
            continue
        ext = entry.suffix.lower()
        if ext in RAW_AV_EXTENSIONS:
            disallowed_files += 1
            continue
        if SAFE_ASSET_FILENAME_RE.match(entry.name):
            asset_count += 1
            used_bytes += entry.stat().st_size

    return {
        "assetCount": asset_count,
        "usedBytes": used_bytes,
        "disallowedFiles": disallowed_files,
    }


def save_optimized_image(
    result: dict[str, Any],
    storage_dir: str | Path,
    *,
    max_storage_bytes: int | None = None,
) -> Path:
    """Persist an optimized image asset atomically under storage_dir within optional quota."""
    filename = result.get("filename", "")
    if not SAFE_ASSET_FILENAME_RE.match(filename):
        raise MediaValidationError(
            "Generated asset filename failed safety validation.",
            status_code=400,
            code="INVALID_FILENAME",
        )

    base_dir = Path(storage_dir).resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    target_path = (base_dir / filename).resolve()
    if target_path.parent != base_dir:
        raise MediaValidationError(
            "Invalid storage path for optimized image.",
            status_code=400,
            code="INVALID_FILENAME",
        )

    if max_storage_bytes is not None and max_storage_bytes > 0:
        existing_bytes = 0
        for entry in base_dir.iterdir():
            if (
                entry.is_file()
                and not entry.name.startswith(".tmp_")
                and entry.name != filename
                and SAFE_ASSET_FILENAME_RE.match(entry.name)
            ):
                existing_bytes += entry.stat().st_size
        if existing_bytes + len(result["data"]) > int(max_storage_bytes):
            raise MediaValidationError(
                "Media storage quota exceeded for free-tier hosting.",
                status_code=507,
                code="STORAGE_QUOTA_EXCEEDED",
            )

    fd, tmp_name = tempfile.mkstemp(
        dir=base_dir,
        prefix=".tmp_img_",
        suffix=result.get("extension", ".webp"),
    )
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(result["data"])
        os.replace(tmp_name, target_path)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise

    return target_path


def _has_traversal_segments(pathname: str) -> bool:
    decoded = unquote(pathname or "")
    for candidate in (pathname or "", decoded):
        segments = candidate.replace("\\", "/").split("/")
        if "." in segments or ".." in segments:
            return True
    return False


def _get_path_extension(pathname: str) -> str:
    clean_path = (pathname or "").split("?", 1)[0].split("#", 1)[0]
    last_segment = clean_path.rsplit("/", 1)[-1]
    dot_idx = last_segment.rfind(".")
    if dot_idx <= 0:
        return ""
    return last_segment[dot_idx:].lower()


def _is_public_hostname(host: str) -> bool:
    cleaned = (host or "").strip().lower().rstrip(".")
    if (
        not cleaned
        or cleaned == "localhost"
        or cleaned.endswith((".localhost", ".local", ".internal"))
    ):
        return False
    if "." not in cleaned:
        return False
    try:
        ipaddress.ip_address(cleaned)
        return False
    except ValueError:
        pass
    return True


def _parse_youtube_embed(parsed) -> dict[str, Any]:
    host = (parsed.hostname or "").lower()
    segments = [seg for seg in parsed.path.split("/") if seg]
    video_id = ""
    is_shorts = False

    if host == "youtu.be" and segments:
        video_id = segments[0]
    elif parsed.path == "/watch":
        video_id = (parse_qs(parsed.query).get("v") or [""])[0]
    elif len(segments) >= 2 and segments[0] in ("shorts", "embed", "live"):
        video_id = segments[1]
        is_shorts = segments[0] == "shorts"

    if not _YOUTUBE_ID_RE.match(video_id):
        raise MediaValidationError(
            "Invalid YouTube video URL or missing video ID.",
            status_code=400,
            code="INVALID_MEDIA_URL",
        )

    return {
        "mediaType": "video",
        "provider": "youtube",
        "canonicalUrl": (
            f"https://www.youtube.com/shorts/{video_id}"
            if is_shorts
            else f"https://www.youtube.com/watch?v={video_id}"
        ),
        "embedUrl": f"https://www.youtube-nocookie.com/embed/{video_id}",
        "renderMode": "iframe",
        "aspectWidth": 9 if is_shorts else 16,
        "aspectHeight": 16 if is_shorts else 9,
        "_allowedTypes": ("video", "reel") if is_shorts else ("video",),
    }


def _parse_vimeo_embed(parsed) -> dict[str, Any]:
    segments = [seg for seg in parsed.path.split("/") if seg]
    video_id = ""

    if (parsed.hostname or "").lower() == "player.vimeo.com":
        if len(segments) >= 2 and segments[0] == "video":
            video_id = segments[1]
    elif segments:
        video_id = segments[-1]

    if not _VIMEO_ID_RE.match(video_id):
        raise MediaValidationError(
            "Invalid Vimeo video URL or missing numeric video ID.",
            status_code=400,
            code="INVALID_MEDIA_URL",
        )

    return {
        "mediaType": "video",
        "provider": "vimeo",
        "canonicalUrl": f"https://vimeo.com/{video_id}",
        "embedUrl": f"https://player.vimeo.com/video/{video_id}",
        "renderMode": "iframe",
        "aspectWidth": 16,
        "aspectHeight": 9,
        "_allowedTypes": ("video",),
    }


def _parse_dailymotion_embed(parsed) -> dict[str, Any]:
    host = (parsed.hostname or "").lower()
    segments = [seg for seg in parsed.path.split("/") if seg]
    video_id = ""

    if host == "dai.ly" and segments:
        video_id = segments[0]
    elif len(segments) >= 2 and segments[0] == "video":
        video_id = segments[1]
    elif len(segments) >= 3 and segments[0] == "embed" and segments[1] == "video":
        video_id = segments[2]

    if not _DAILYMOTION_ID_RE.match(video_id):
        raise MediaValidationError(
            "Invalid Dailymotion video URL or missing video ID.",
            status_code=400,
            code="INVALID_MEDIA_URL",
        )

    return {
        "mediaType": "video",
        "provider": "dailymotion",
        "canonicalUrl": f"https://www.dailymotion.com/video/{video_id}",
        "embedUrl": f"https://www.dailymotion.com/embed/video/{video_id}",
        "renderMode": "iframe",
        "aspectWidth": 16,
        "aspectHeight": 9,
        "_allowedTypes": ("video",),
    }


def _parse_instagram_embed(parsed) -> dict[str, Any]:
    segments = [seg for seg in parsed.path.split("/") if seg]
    if len(segments) >= 3 and segments[-2] == "embed" and segments[-1] == "captioned":
        segments = segments[:-2]
    elif len(segments) >= 3 and segments[-1] == "embed":
        segments = segments[:-1]

    kind = ""
    shortcode = ""
    if len(segments) >= 2 and segments[0] in ("reel", "reels", "p", "tv"):
        kind, shortcode = segments[0], segments[1]
    elif len(segments) >= 3 and segments[1] in ("reel", "reels", "p", "tv"):
        kind, shortcode = segments[1], segments[2]

    if kind and _INSTAGRAM_SHORTCODE_RE.match(shortcode):
        norm_kind = "reel" if kind in ("reel", "reels") else kind
        canonical_url = f"https://www.instagram.com/{norm_kind}/{shortcode}/"
        embed_url = f"https://www.instagram.com/{norm_kind}/{shortcode}/embed/"
        if norm_kind == "reel":
            media_type = "reel"
            allowed_types: tuple[str, ...] = ("reel", "video")
        elif norm_kind == "p":
            media_type = "post"
            allowed_types = ("post", "image", "video", "reel")
        else:
            media_type = "video"
            allowed_types = ("video", "reel", "post")
        result = {
            "mediaType": media_type,
            "provider": "instagram",
            "canonicalUrl": canonical_url,
            "embedUrl": embed_url,
            "renderMode": "iframe",
            "_allowedTypes": allowed_types,
        }
        if norm_kind in ("reel", "tv"):
            result["aspectWidth"] = 9
            result["aspectHeight"] = 16
        return result

    if (
        len(segments) >= 3
        and segments[0] == "stories"
        and _HANDLE_RE.match(segments[1])
        and _ALNUM_SLUG_RE.match(segments[2])
    ):
        return {
            "mediaType": "post",
            "provider": "instagram",
            "canonicalUrl": f"https://www.instagram.com/stories/{segments[1]}/{segments[2]}/",
            "embedUrl": "",
            "renderMode": "card",
            "_allowedTypes": ("post", "reel", "video", "image"),
        }

    if (
        len(segments) >= 2
        and segments[0] == "share"
        and all(_ALNUM_SLUG_RE.match(seg) for seg in segments[1:])
    ):
        media_type = "reel" if (len(segments) >= 3 and segments[1] == "reel") else "post"
        return {
            "mediaType": media_type,
            "provider": "instagram",
            "canonicalUrl": f"https://www.instagram.com/{'/'.join(segments)}/",
            "embedUrl": "",
            "renderMode": "card",
            "_allowedTypes": ("post", "reel", "video", "image"),
        }

    raise MediaValidationError(
        "Invalid Instagram reel, post, or story URL.",
        status_code=400,
        code="INVALID_MEDIA_URL",
    )


def _parse_facebook_embed(parsed, _depth: int = 0) -> dict[str, Any]:
    host = (parsed.hostname or "").lower()
    segments = [seg for seg in parsed.path.split("/") if seg]
    clean_path = parsed.path.rstrip("/")
    qs = parse_qs(parsed.query)

    if clean_path in ("/plugins/video.php", "/plugins/post.php"):
        if _depth > 0:
            raise MediaValidationError(
                "Invalid nested Facebook plugin URL.",
                status_code=400,
                code="INVALID_MEDIA_URL",
            )
        href = (qs.get("href") or [""])[0].strip()
        if not href:
            raise MediaValidationError(
                "Facebook plugin URL is missing target 'href' parameter.",
                status_code=400,
                code="INVALID_MEDIA_URL",
            )
        if re.search(r"[\s\x00-\x1f\x7f<>\"']", href):
            raise MediaValidationError(
                "Facebook plugin target URL contains unsafe characters.",
                status_code=400,
                code="UNSAFE_MEDIA_URL",
            )
        inner = urlsplit(href)
        if inner.scheme.lower() != "https":
            raise MediaValidationError(
                "Facebook plugin target URL must use HTTPS.",
                status_code=400,
                code="INSECURE_MEDIA_URL",
            )
        if inner.username or inner.password or _has_traversal_segments(inner.path):
            raise MediaValidationError(
                "Facebook plugin target URL is unsafe.",
                status_code=400,
                code="UNSAFE_MEDIA_URL",
            )
        inner_host = (inner.hostname or "").lower()
        if inner_host not in _FACEBOOK_HOSTS:
            raise MediaValidationError(
                "Facebook plugin target URL must point to facebook.com.",
                status_code=400,
                code="UNTRUSTED_MEDIA_DOMAIN",
            )
        return _parse_facebook_embed(inner, _depth=_depth + 1)

    if host == "fb.watch":
        if not segments or not _ALNUM_SLUG_RE.match(segments[0]):
            raise MediaValidationError(
                "Invalid fb.watch video URL.",
                status_code=400,
                code="INVALID_MEDIA_URL",
            )
        return {
            "mediaType": "video",
            "provider": "facebook",
            "canonicalUrl": f"https://fb.watch/{segments[0]}/",
            "embedUrl": "",
            "renderMode": "card",
            "_allowedTypes": ("video", "reel", "post"),
        }

    if len(segments) >= 2 and segments[0] == "share" and all(_ALNUM_SLUG_RE.match(s) for s in segments[1:]):
        sub = segments[1]
        if sub == "r" and len(segments) >= 3:
            share_type = "reel"
        elif sub == "v" and len(segments) >= 3:
            share_type = "video"
        else:
            share_type = "post"
        return {
            "mediaType": share_type,
            "provider": "facebook",
            "canonicalUrl": f"https://www.facebook.com/{'/'.join(segments)}/",
            "embedUrl": "",
            "renderMode": "card",
            "_allowedTypes": ("post", "reel", "video", "image"),
        }

    if len(segments) >= 2 and segments[0] in ("reel", "reels") and _ALNUM_SLUG_RE.match(segments[1]):
        canonical_url = f"https://www.facebook.com/reel/{segments[1]}"
        embed_url = (
            f"https://www.facebook.com/plugins/video.php?href={quote(canonical_url, safe='')}"
            "&show_text=false"
        )
        return {
            "mediaType": "reel",
            "provider": "facebook",
            "canonicalUrl": canonical_url,
            "embedUrl": embed_url,
            "renderMode": "iframe",
            "aspectWidth": 9,
            "aspectHeight": 16,
            "_allowedTypes": ("reel", "video"),
        }

    if clean_path in ("/watch", "/video.php", "/video/video.php"):
        video_id = (qs.get("v") or [""])[0].strip()
        if not video_id or not _ALNUM_SLUG_RE.match(video_id):
            raise MediaValidationError(
                "Invalid Facebook watch URL or missing video ID.",
                status_code=400,
                code="INVALID_MEDIA_URL",
            )
        canonical_url = f"https://www.facebook.com/watch/?v={video_id}"
        embed_url = (
            f"https://www.facebook.com/plugins/video.php?href={quote(canonical_url, safe='')}"
            "&show_text=false"
        )
        return {
            "mediaType": "video",
            "provider": "facebook",
            "canonicalUrl": canonical_url,
            "embedUrl": embed_url,
            "renderMode": "iframe",
            "aspectWidth": 16,
            "aspectHeight": 9,
            "_allowedTypes": ("video", "reel"),
        }

    if "videos" in segments and len(segments) >= 2 and segments[-1] != "videos":
        canonical_url = f"https://www.facebook.com/{'/'.join(segments)}"
        embed_url = (
            f"https://www.facebook.com/plugins/video.php?href={quote(canonical_url, safe='')}"
            "&show_text=false"
        )
        return {
            "mediaType": "video",
            "provider": "facebook",
            "canonicalUrl": canonical_url,
            "embedUrl": embed_url,
            "renderMode": "iframe",
            "aspectWidth": 16,
            "aspectHeight": 9,
            "_allowedTypes": ("video", "reel"),
        }

    canonical_post_url = ""
    if clean_path in ("/permalink.php", "/story.php"):
        story_fbid = (qs.get("story_fbid") or [""])[0].strip()
        page_id = (qs.get("id") or [""])[0].strip()
        if story_fbid and page_id and _ALNUM_SLUG_RE.match(story_fbid) and _ALNUM_SLUG_RE.match(page_id):
            canonical_post_url = (
                f"https://www.facebook.com{clean_path}"
                f"?story_fbid={quote(story_fbid, safe='')}&id={quote(page_id, safe='')}"
            )
    elif clean_path in ("/photo", "/photo.php"):
        fbid = (qs.get("fbid") or [""])[0].strip()
        if fbid and _ALNUM_SLUG_RE.match(fbid):
            canonical_post_url = f"https://www.facebook.com/photo/?fbid={quote(fbid, safe='')}"
    elif len(segments) >= 3 and (
        "posts" in segments
        or (segments[0] == "groups" and "permalink" in segments)
        or "photos" in segments
    ):
        canonical_post_url = f"https://www.facebook.com/{'/'.join(segments)}"

    if canonical_post_url:
        embed_url = (
            f"https://www.facebook.com/plugins/post.php?href={quote(canonical_post_url, safe='')}"
            "&show_text=true"
        )
        return {
            "mediaType": "post",
            "provider": "facebook",
            "canonicalUrl": canonical_post_url,
            "embedUrl": embed_url,
            "renderMode": "iframe",
            "_allowedTypes": ("post", "image", "video"),
        }

    raise MediaValidationError(
        "Invalid Facebook reel, video, post, or photo URL.",
        status_code=400,
        code="INVALID_MEDIA_URL",
    )


def _parse_tiktok_embed(parsed) -> dict[str, Any]:
    host = (parsed.hostname or "").lower()
    segments = [seg for seg in parsed.path.split("/") if seg]

    if host in _TIKTOK_SHORT_HOSTS:
        if not segments or not _ALNUM_SLUG_RE.match(segments[0]):
            raise MediaValidationError(
                "Invalid shortened TikTok URL.",
                status_code=400,
                code="INVALID_MEDIA_URL",
            )
        return {
            "mediaType": "reel",
            "provider": "tiktok",
            "canonicalUrl": f"https://{host}/{segments[0]}",
            "embedUrl": "",
            "renderMode": "card",
            "_allowedTypes": ("reel", "video", "post"),
        }

    if len(segments) >= 2 and segments[0] == "t" and _ALNUM_SLUG_RE.match(segments[1]):
        return {
            "mediaType": "reel",
            "provider": "tiktok",
            "canonicalUrl": f"https://www.tiktok.com/t/{segments[1]}",
            "embedUrl": "",
            "renderMode": "card",
            "_allowedTypes": ("reel", "video", "post"),
        }

    if (
        len(segments) >= 3
        and segments[0].startswith("@")
        and len(segments[0]) > 1
        and segments[1] in ("video", "photo")
        and _NUMERIC_ID_RE.match(segments[2])
    ):
        user, kind, item_id = segments[0], segments[1], segments[2]
        if kind == "video":
            return {
                "mediaType": "reel",
                "provider": "tiktok",
                "canonicalUrl": f"https://www.tiktok.com/{user}/video/{item_id}",
                "embedUrl": f"https://www.tiktok.com/embed/v2/{item_id}",
                "renderMode": "iframe",
                "aspectWidth": 9,
                "aspectHeight": 16,
                "_allowedTypes": ("reel", "video"),
            }
        return {
            "mediaType": "post",
            "provider": "tiktok",
            "canonicalUrl": f"https://www.tiktok.com/{user}/photo/{item_id}",
            "embedUrl": "",
            "renderMode": "card",
            "_allowedTypes": ("post", "image"),
        }

    if (
        len(segments) >= 2
        and (segments[0] == "video" or segments[0] == "embed")
        and _NUMERIC_ID_RE.match(segments[-1])
    ):
        item_id = segments[-1]
        return {
            "mediaType": "reel",
            "provider": "tiktok",
            "canonicalUrl": f"https://www.tiktok.com/embed/v2/{item_id}",
            "embedUrl": f"https://www.tiktok.com/embed/v2/{item_id}",
            "renderMode": "iframe",
            "aspectWidth": 9,
            "aspectHeight": 16,
            "_allowedTypes": ("reel", "video"),
        }

    raise MediaValidationError(
        "Invalid TikTok video or photo URL.",
        status_code=400,
        code="INVALID_MEDIA_URL",
    )


def _parse_x_embed(parsed) -> dict[str, Any]:
    segments = [seg for seg in parsed.path.split("/") if seg]
    status_id = ""
    if len(segments) >= 3 and segments[1] == "status" and _NUMERIC_ID_RE.match(segments[2]):
        status_id = segments[2]
        canonical_url = f"https://x.com/{segments[0]}/status/{status_id}"
    elif (
        len(segments) >= 4
        and segments[0] == "i"
        and segments[1] == "web"
        and segments[2] == "status"
        and _NUMERIC_ID_RE.match(segments[3])
    ):
        status_id = segments[3]
        canonical_url = f"https://x.com/i/web/status/{status_id}"
    else:
        canonical_url = ""

    if not status_id:
        raise MediaValidationError(
            "Invalid X/Twitter post URL.",
            status_code=400,
            code="INVALID_MEDIA_URL",
        )

    return {
        "mediaType": "post",
        "provider": "x",
        "canonicalUrl": canonical_url,
        "embedUrl": "",
        "renderMode": "card",
        "_allowedTypes": ("post", "video", "image"),
    }


def _parse_threads_embed(parsed) -> dict[str, Any]:
    segments = [seg for seg in parsed.path.split("/") if seg]
    if len(segments) >= 4 and segments[-1] == "embed":
        segments = segments[:-1]

    if (
        len(segments) >= 3
        and segments[0].startswith("@")
        and len(segments[0]) > 1
        and segments[1] == "post"
        and _ALNUM_SLUG_RE.match(segments[2])
    ):
        canonical_url = f"https://www.threads.net/{segments[0]}/post/{segments[2]}"
        return {
            "mediaType": "post",
            "provider": "threads",
            "canonicalUrl": canonical_url,
            "embedUrl": f"{canonical_url}/embed",
            "renderMode": "iframe",
            "_allowedTypes": ("post", "video", "reel", "image"),
        }

    if len(segments) >= 2 and segments[0] == "t" and _ALNUM_SLUG_RE.match(segments[1]):
        canonical_url = f"https://www.threads.net/t/{segments[1]}"
        return {
            "mediaType": "post",
            "provider": "threads",
            "canonicalUrl": canonical_url,
            "embedUrl": "",
            "renderMode": "card",
            "_allowedTypes": ("post", "video", "reel", "image"),
        }

    raise MediaValidationError(
        "Invalid Threads post URL.",
        status_code=400,
        code="INVALID_MEDIA_URL",
    )


def _parse_linkedin_embed(parsed) -> dict[str, Any]:
    segments = [seg for seg in parsed.path.split("/") if seg]
    if len(segments) >= 4 and segments[0] == "embed" and segments[1] == "feed" and segments[2] == "update":
        urn = segments[3]
        if urn.startswith("urn:li:"):
            canonical_url = f"https://www.linkedin.com/feed/update/{urn}"
            return {
                "mediaType": "post",
                "provider": "linkedin",
                "canonicalUrl": canonical_url,
                "embedUrl": f"https://www.linkedin.com/embed/feed/update/{urn}",
                "renderMode": "iframe",
                "_allowedTypes": ("post", "video", "image"),
            }

    if len(segments) >= 3 and segments[0] == "feed" and segments[1] == "update":
        urn = segments[2]
        canonical_url = f"https://www.linkedin.com/feed/update/{urn}"
        if urn.startswith("urn:li:"):
            return {
                "mediaType": "post",
                "provider": "linkedin",
                "canonicalUrl": canonical_url,
                "embedUrl": f"https://www.linkedin.com/embed/feed/update/{urn}",
                "renderMode": "iframe",
                "_allowedTypes": ("post", "video", "image"),
            }
        return {
            "mediaType": "post",
            "provider": "linkedin",
            "canonicalUrl": canonical_url,
            "embedUrl": "",
            "renderMode": "card",
            "_allowedTypes": ("post", "video", "image"),
        }

    if len(segments) >= 2 and segments[0] in ("posts", "pulse"):
        canonical_url = f"https://www.linkedin.com/{'/'.join(segments)}"
        activity_match = re.search(r"activity-(\d+)", segments[1]) if segments[0] == "posts" else None
        if activity_match:
            urn = f"urn:li:activity:{activity_match.group(1)}"
            return {
                "mediaType": "post",
                "provider": "linkedin",
                "canonicalUrl": canonical_url,
                "embedUrl": f"https://www.linkedin.com/embed/feed/update/{urn}",
                "renderMode": "iframe",
                "_allowedTypes": ("post", "video", "image"),
            }
        return {
            "mediaType": "post",
            "provider": "linkedin",
            "canonicalUrl": canonical_url,
            "embedUrl": "",
            "renderMode": "card",
            "_allowedTypes": ("post", "video", "image"),
        }

    raise MediaValidationError(
        "Invalid LinkedIn post URL.",
        status_code=400,
        code="INVALID_MEDIA_URL",
    )


def _parse_telegram_embed(parsed) -> dict[str, Any]:
    segments = [seg for seg in parsed.path.split("/") if seg]
    if len(segments) >= 3 and segments[0] == "s" and _HANDLE_RE.match(segments[1]) and _NUMERIC_ID_RE.match(segments[2]):
        canonical_url = f"https://t.me/{segments[1]}/{segments[2]}"
    elif len(segments) >= 2 and _HANDLE_RE.match(segments[0]) and _NUMERIC_ID_RE.match(segments[1]):
        canonical_url = f"https://t.me/{segments[0]}/{segments[1]}"
    else:
        raise MediaValidationError(
            "Invalid Telegram channel post URL.",
            status_code=400,
            code="INVALID_MEDIA_URL",
        )

    return {
        "mediaType": "post",
        "provider": "telegram",
        "canonicalUrl": canonical_url,
        "embedUrl": f"{canonical_url}?embed=1",
        "renderMode": "iframe",
        "_allowedTypes": ("post", "video", "image", "audio"),
    }


def _parse_soundcloud_embed(parsed) -> dict[str, Any]:
    host = (parsed.hostname or "").lower()
    if host == "w.soundcloud.com":
        if parsed.path.rstrip("/") != "/player":
            raise MediaValidationError(
                "Invalid SoundCloud player embed URL.",
                status_code=400,
                code="INVALID_MEDIA_URL",
            )
        inner_url = (parse_qs(parsed.query).get("url") or [""])[0].strip()
        if not inner_url:
            raise MediaValidationError(
                "SoundCloud player URL is missing target 'url' parameter.",
                status_code=400,
                code="INVALID_MEDIA_URL",
            )
        inner_parsed = urlsplit(inner_url)
        inner_host = (inner_parsed.hostname or "").lower()
        if inner_parsed.scheme.lower() != "https":
            raise MediaValidationError(
                "SoundCloud target URL must use HTTPS.",
                status_code=400,
                code="INSECURE_MEDIA_URL",
            )
        if inner_host not in _SOUNDCLOUD_PAGE_HOSTS:
            raise MediaValidationError(
                "SoundCloud player target URL must point to soundcloud.com.",
                status_code=400,
                code="UNTRUSTED_MEDIA_DOMAIN",
            )
        track_path = inner_parsed.path
    else:
        track_path = parsed.path

    segments = [seg for seg in track_path.split("/") if seg]
    if not segments:
        raise MediaValidationError(
            "SoundCloud URL must include a track or playlist path.",
            status_code=400,
            code="INVALID_MEDIA_URL",
        )

    canonical_url = f"https://soundcloud.com/{'/'.join(segments)}"
    encoded_target = quote(canonical_url, safe="")
    embed_url = (
        f"https://w.soundcloud.com/player/?url={encoded_target}"
        "&auto_play=false&show_teaser=false"
    )
    return {
        "mediaType": "audio",
        "provider": "soundcloud",
        "canonicalUrl": canonical_url,
        "embedUrl": embed_url,
        "renderMode": "iframe",
        "_allowedTypes": ("audio",),
    }


def _parse_spotify_embed(parsed) -> dict[str, Any]:
    segments = [seg for seg in parsed.path.split("/") if seg]
    if segments and segments[0].startswith("intl-"):
        segments = segments[1:]
    if segments and segments[0] == "embed":
        segments = segments[1:]

    if (
        len(segments) < 2
        or segments[0] not in ("track", "episode", "show", "playlist", "album")
        or not _SPOTIFY_ID_RE.match(segments[1])
    ):
        raise MediaValidationError(
            "Invalid Spotify audio URL.",
            status_code=400,
            code="INVALID_MEDIA_URL",
        )

    kind, item_id = segments[0], segments[1]
    return {
        "mediaType": "audio",
        "provider": "spotify",
        "canonicalUrl": f"https://open.spotify.com/{kind}/{item_id}",
        "embedUrl": f"https://open.spotify.com/embed/{kind}/{item_id}",
        "renderMode": "iframe",
        "_allowedTypes": ("audio",),
    }


def _parse_google_drive_embed(parsed) -> dict[str, Any]:
    segments = [seg for seg in parsed.path.split("/") if seg]
    file_id = ""

    if len(segments) >= 3 and segments[0] == "file" and segments[1] == "d":
        file_id = segments[2]
    elif parsed.path.rstrip("/") in ("/open", "/uc"):
        file_id = (parse_qs(parsed.query).get("id") or [""])[0]

    if not _DRIVE_ID_RE.match(file_id):
        raise MediaValidationError(
            "Invalid Google Drive media URL or missing file ID.",
            status_code=400,
            code="INVALID_MEDIA_URL",
        )

    return {
        "mediaType": "audio",
        "provider": "google_drive",
        "canonicalUrl": f"https://drive.google.com/file/d/{file_id}/view",
        "embedUrl": f"https://drive.google.com/file/d/{file_id}/preview",
        "renderMode": "iframe",
        "_allowedTypes": ("audio", "video", "image", "post"),
    }


def _parse_google_photos_embed(parsed) -> dict[str, Any]:
    host = (parsed.hostname or "").lower()
    segments = [seg for seg in parsed.path.split("/") if seg]
    if not segments:
        raise MediaValidationError(
            "Invalid Google Photos link.",
            status_code=400,
            code="INVALID_MEDIA_URL",
        )

    if host == "photos.app.goo.gl":
        canonical_url = f"https://photos.app.goo.gl/{segments[0]}"
    elif (
        segments[0] in ("share", "photo", "album")
        or (len(segments) >= 3 and segments[0] == "u" and segments[2] in ("share", "photo", "album"))
    ):
        canonical_url = f"https://photos.google.com/{'/'.join(segments)}"
        if parsed.query:
            canonical_url = f"{canonical_url}?{parsed.query}"
    else:
        raise MediaValidationError(
            "Invalid Google Photos album or photo URL.",
            status_code=400,
            code="INVALID_MEDIA_URL",
        )

    return {
        "mediaType": "image",
        "provider": "google_photos",
        "canonicalUrl": canonical_url,
        "embedUrl": "",
        "renderMode": "card",
        "_allowedTypes": ("image", "post", "video"),
    }


def _parse_canva_embed(parsed) -> dict[str, Any]:
    segments = [seg for seg in parsed.path.split("/") if seg]
    if len(segments) < 2 or segments[0] != "design" or not _CANVA_ID_RE.match(segments[1]):
        raise MediaValidationError(
            "Invalid Canva design URL.",
            status_code=400,
            code="INVALID_MEDIA_URL",
        )

    design_id = segments[1]
    return {
        "mediaType": "post",
        "provider": "canva",
        "canonicalUrl": f"https://www.canva.com/design/{design_id}/view",
        "embedUrl": f"https://www.canva.com/design/{design_id}/view?embed",
        "renderMode": "iframe",
        "_allowedTypes": ("post", "image", "video"),
    }


def _parse_external_image_url(parsed, cleaned: str) -> dict[str, Any]:
    host = (parsed.hostname or "").lower()
    if not _is_public_hostname(host):
        raise MediaValidationError(
            f"Domain '{host}' is not allowed for external image links.",
            status_code=400,
            code="UNTRUSTED_MEDIA_DOMAIN",
        )
    ext = _get_path_extension(parsed.path)
    if ext == ".svg" or ext in RAW_AV_EXTENSIONS:
        raise MediaValidationError(
            f"Unsupported external image extension '{ext}'.",
            status_code=400,
            code="UNSUPPORTED_MEDIA_TYPE",
        )
    return {
        "mediaType": "image",
        "provider": "external_image",
        "canonicalUrl": cleaned,
        "embedUrl": "",
        "renderMode": "image",
        "_allowedTypes": ("image",),
    }


_SHORT_URL_CACHE_MAX = 256
_short_url_cache: dict[str, str] = {}
_short_url_cache_lock = threading.Lock()
_media_dimensions_cache: dict[str, tuple[int, int]] = {}
_media_dimensions_cache_lock = threading.Lock()

_DIM_PROBE_HOSTS = frozenset({
    *_FACEBOOK_HOSTS,
    *_INSTAGRAM_HOSTS,
    *_TIKTOK_HOSTS,
    *_YOUTUBE_HOSTS,
    *_VIMEO_HOSTS,
    *_DAILYMOTION_HOSTS,
})

_OG_VIDEO_W_1 = re.compile(
    r'<meta[^>]+property=["\']og:video:width["\'][^>]+content=["\'](\d+)["\']',
    re.IGNORECASE,
)
_OG_VIDEO_W_2 = re.compile(
    r'<meta[^>]+content=["\'](\d+)["\'][^>]+property=["\']og:video:width["\']',
    re.IGNORECASE,
)
_OG_VIDEO_H_1 = re.compile(
    r'<meta[^>]+property=["\']og:video:height["\'][^>]+content=["\'](\d+)["\']',
    re.IGNORECASE,
)
_OG_VIDEO_H_2 = re.compile(
    r'<meta[^>]+content=["\'](\d+)["\'][^>]+property=["\']og:video:height["\']',
    re.IGNORECASE,
)
_OG_IMAGE_W_1 = re.compile(
    r'<meta[^>]+property=["\']og:image:width["\'][^>]+content=["\'](\d+)["\']',
    re.IGNORECASE,
)
_OG_IMAGE_W_2 = re.compile(
    r'<meta[^>]+content=["\'](\d+)["\'][^>]+property=["\']og:image:width["\']',
    re.IGNORECASE,
)
_OG_IMAGE_H_1 = re.compile(
    r'<meta[^>]+property=["\']og:image:height["\'][^>]+content=["\'](\d+)["\']',
    re.IGNORECASE,
)
_OG_IMAGE_H_2 = re.compile(
    r'<meta[^>]+content=["\'](\d+)["\'][^>]+property=["\']og:image:height["\']',
    re.IGNORECASE,
)
_FB_ORIG_W_RE = re.compile(r'\\?"original_width\\?"\s*:\s*(\d{3,4})')
_FB_ORIG_H_RE = re.compile(r'\\?"original_height\\?"\s*:\s*(\d{3,4})')
_VIDEO_WIDTH_RE = re.compile(r'\\?"video_width\\?"\s*:\s*(\d{3,4})')
_VIDEO_HEIGHT_RE = re.compile(r'\\?"video_height\\?"\s*:\s*(\d{3,4})')
_DATA_VIDEO_W_RE = re.compile(r'data-video-width=["\'](\d{2,4})["\']', re.IGNORECASE)
_DATA_VIDEO_H_RE = re.compile(r'data-video-height=["\'](\d{2,4})["\']', re.IGNORECASE)
_VIDEO_TAG_WH_1 = re.compile(
    r'<video\b[^>]*\bwidth=["\'](\d{2,4})["\'][^>]*\bheight=["\'](\d{2,4})["\']',
    re.IGNORECASE,
)
_VIDEO_TAG_WH_2 = re.compile(
    r'<video\b[^>]*\bheight=["\'](\d{2,4})["\'][^>]*\bwidth=["\'](\d{2,4})["\']',
    re.IGNORECASE,
)
_FB_VIDEO_JSON_PAIR_RE = re.compile(
    r'(?:playable_url|browser_native_sd_url|videoData|preferred_thumbnail|dash_manifest)[\s\S]{0,600}?'
    r'\\?"width\\?"\s*:\s*(\d{3,4})\s*,\s*\\?"height\\?"\s*:\s*(\d{3,4})',
    re.IGNORECASE,
)
_PLUGIN_PADDING_RATIO_RE = re.compile(
    r'padding-(?:bottom|top)\s*:\s*(\d+(?:\.\d+)?)%', re.IGNORECASE
)

_OG_URL_META_RE_1 = re.compile(
    r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_OG_URL_META_RE_2 = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:url["\']',
    re.IGNORECASE,
)
_CANONICAL_LINK_RE_1 = re.compile(
    r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_CANONICAL_LINK_RE_2 = re.compile(
    r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']canonical["\']',
    re.IGNORECASE,
)
_FB_HTML_VIDEO_URL_RE = re.compile(
    r'https://(?:www\.|m\.|web\.)?facebook\.com/(?:reel/\d+|watch/\?v=\d+|[A-Za-z0-9._-]+/videos/\d+|groups/\d+/videos/\d+|[A-Za-z0-9._-]+/posts/[A-Za-z0-9_-]+)',
    re.IGNORECASE,
)
_FB_HTML_VIDEO_ID_RE = re.compile(r'\\?"video_id\\?"\s*:\s*\\?"(\d{6,30})\\?"')
_TIKTOK_HTML_URL_RE = re.compile(
    r'https://(?:www\.)?tiktok\.com/@[A-Za-z0-9._-]+/video/\d+',
    re.IGNORECASE,
)
_IG_HTML_URL_RE = re.compile(
    r'https://(?:www\.)?instagram\.com/(?:reel|p|tv)/[A-Za-z0-9_-]{5,64}/?',
    re.IGNORECASE,
)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _short_link_allowed_hosts(parsed) -> frozenset[str] | None:
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    if host == "fb.watch" or (host in _FACEBOOK_HOSTS and path.startswith("/share/")):
        return _FACEBOOK_HOSTS
    if host in _TIKTOK_SHORT_HOSTS or (host in _TIKTOK_HOSTS and path.startswith("/t/")):
        return _TIKTOK_HOSTS
    if host in _INSTAGRAM_HOSTS and path.startswith("/share/"):
        return _INSTAGRAM_HOSTS
    return None


def _is_safe_same_platform_url(
    candidate: str,
    base_url: str,
    allowed_hosts: frozenset[str],
) -> str | None:
    if not candidate or not isinstance(candidate, str):
        return None
    joined = urljoin(base_url, html.unescape(candidate.strip()))
    if re.search(r"[\s\x00-\x1f\x7f<>\"']", joined):
        return None
    parsed = urlsplit(joined)
    host = (parsed.hostname or "").lower()
    path_lower = (parsed.path or "").lower()
    if (
        parsed.scheme.lower() != "https"
        or parsed.username
        or parsed.password
        or _has_traversal_segments(parsed.path)
        or host not in allowed_hosts
        or "/login" in path_lower
        or "/accounts/login" in path_lower
    ):
        return None
    return joined


def _extract_canonical_from_html(
    html_text: str,
    base_url: str,
    allowed_hosts: frozenset[str],
) -> str | None:
    if not html_text:
        return None

    for pattern in (
        _OG_URL_META_RE_1,
        _OG_URL_META_RE_2,
        _CANONICAL_LINK_RE_1,
        _CANONICAL_LINK_RE_2,
    ):
        match = pattern.search(html_text)
        if match:
            safe_url = _is_safe_same_platform_url(
                match.group(1), base_url, allowed_hosts
            )
            if safe_url and _short_link_allowed_hosts(urlsplit(safe_url)) is None:
                return safe_url

    if allowed_hosts is _FACEBOOK_HOSTS:
        unescaped_html = html_text.replace("\\/", "/")
        fb_post_match = re.search(
            r'https://(?:www\.|m\.|web\.)?facebook\.com/(?:'
            r'permalink\.php\?story_fbid=[A-Za-z0-9._-]+&(?:amp;)?id=[A-Za-z0-9._-]+|'
            r'story\.php\?story_fbid=[A-Za-z0-9._-]+&(?:amp;)?id=[A-Za-z0-9._-]+|'
            r'[A-Za-z0-9._-]+/posts/[A-Za-z0-9._-]+)',
            unescaped_html,
            re.IGNORECASE,
        )
        if fb_post_match:
            safe_url = _is_safe_same_platform_url(
                fb_post_match.group(0), base_url, allowed_hosts
            )
            if safe_url:
                return safe_url
        fb_match = _FB_HTML_VIDEO_URL_RE.search(unescaped_html)
        if fb_match:
            safe_url = _is_safe_same_platform_url(
                fb_match.group(0), base_url, allowed_hosts
            )
            if safe_url:
                return safe_url
        id_match = _FB_HTML_VIDEO_ID_RE.search(html_text)
        if id_match:
            vid = id_match.group(1)
            if "/share/r/" in base_url:
                return f"https://www.facebook.com/reel/{vid}"
            return f"https://www.facebook.com/watch/?v={vid}"
    elif allowed_hosts is _TIKTOK_HOSTS:
        tt_match = _TIKTOK_HTML_URL_RE.search(html_text)
        if tt_match:
            safe_url = _is_safe_same_platform_url(
                tt_match.group(0), base_url, allowed_hosts
            )
            if safe_url:
                return safe_url
    elif allowed_hosts is _INSTAGRAM_HOSTS:
        ig_match = _IG_HTML_URL_RE.search(html_text)
        if ig_match:
            safe_url = _is_safe_same_platform_url(
                ig_match.group(0), base_url, allowed_hosts
            )
            if safe_url:
                return safe_url

    return None


def _valid_dimension_pair(width: int, height: int) -> tuple[int, int] | None:
    if width < 100 or width > 8000 or height < 100 or height > 8000:
        return None
    ratio = width / float(height)
    if ratio < 0.35 or ratio > 3.0:
        return None
    return width, height


def _extract_dimensions_from_html(html_text: str) -> tuple[int, int] | None:
    if not html_text:
        return None

    for w_patterns, h_patterns in (
        ((_DATA_VIDEO_W_RE,), (_DATA_VIDEO_H_RE,)),
    ):
        w_m = w_patterns[0].search(html_text)
        h_m = h_patterns[0].search(html_text)
        if w_m and h_m:
            pair = _valid_dimension_pair(int(w_m.group(1)), int(h_m.group(1)))
            if pair is not None:
                return pair

    tag_match_1 = _VIDEO_TAG_WH_1.search(html_text)
    if tag_match_1:
        pair = _valid_dimension_pair(int(tag_match_1.group(1)), int(tag_match_1.group(2)))
        if pair is not None:
            return pair

    tag_match_2 = _VIDEO_TAG_WH_2.search(html_text)
    if tag_match_2:
        pair = _valid_dimension_pair(int(tag_match_2.group(2)), int(tag_match_2.group(1)))
        if pair is not None:
            return pair

    for w_patterns, h_patterns in (
        ((_OG_VIDEO_W_1, _OG_VIDEO_W_2), (_OG_VIDEO_H_1, _OG_VIDEO_H_2)),
        ((_OG_IMAGE_W_1, _OG_IMAGE_W_2), (_OG_IMAGE_H_1, _OG_IMAGE_H_2)),
        ((_FB_ORIG_W_RE,), (_FB_ORIG_H_RE,)),
        ((_VIDEO_WIDTH_RE,), (_VIDEO_HEIGHT_RE,)),
    ):
        w_val = None
        h_val = None
        for wp in w_patterns:
            m = wp.search(html_text)
            if m:
                w_val = int(m.group(1))
                break
        for hp in h_patterns:
            m = hp.search(html_text)
            if m:
                h_val = int(m.group(1))
                break
        if w_val is not None and h_val is not None:
            pair = _valid_dimension_pair(w_val, h_val)
            if pair is not None:
                return pair

    for match in _FB_VIDEO_JSON_PAIR_RE.finditer(html_text):
        pair = _valid_dimension_pair(int(match.group(1)), int(match.group(2)))
        if pair is not None:
            return pair

    pad_match = _PLUGIN_PADDING_RATIO_RE.search(html_text)
    if pad_match:
        pct = float(pad_match.group(1))
        if 33.0 <= pct <= 250.0:
            pair = _valid_dimension_pair(1000, round(pct * 10))
            if pair is not None:
                return pair

    return None


def probe_media_dimensions(
    raw_url: str,
    *,
    timeout: float = 4.0,
    opener: Any = None,
    use_cache: bool = True,
) -> tuple[int, int] | None:
    """Fetch bounded HTML metadata from allowlisted video/reel URLs to infer original aspect ratio."""
    if not isinstance(raw_url, str) or not raw_url.strip():
        return None
    cleaned = raw_url.strip()
    if re.search(r"[\s\x00-\x1f\x7f<>\"']", cleaned):
        return None
    parsed = urlsplit(cleaned)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme.lower() != "https"
        or parsed.username
        or parsed.password
        or host not in _DIM_PROBE_HOSTS
    ):
        return None

    should_cache = opener is None and use_cache
    if should_cache:
        with _media_dimensions_cache_lock:
            cached = _media_dimensions_cache.get(cleaned)
        if cached is not None:
            return cached

    active_opener = opener or urllib.request.build_opener()
    req = urllib.request.Request(
        cleaned,
        method="GET",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    html_snippet = ""
    try:
        resp = active_opener.open(req, timeout=timeout)
        try:
            read_fn = getattr(resp, "read", None)
            if callable(read_fn):
                raw_body = read_fn(262144)
                if isinstance(raw_body, bytes):
                    html_snippet = raw_body.decode("utf-8", errors="ignore")
                elif isinstance(raw_body, str):
                    html_snippet = raw_body
        finally:
            close_fn = getattr(resp, "close", None)
            if callable(close_fn):
                close_fn()
    except Exception:
        return None

    dims = _extract_dimensions_from_html(html_snippet)
    if dims is not None and should_cache:
        with _media_dimensions_cache_lock:
            if len(_media_dimensions_cache) >= _SHORT_URL_CACHE_MAX:
                _media_dimensions_cache.pop(next(iter(_media_dimensions_cache)), None)
            _media_dimensions_cache[cleaned] = dims
    return dims


def resolve_short_social_url(
    raw_url: str,
    *,
    timeout: float = 4.0,
    max_hops: int = 5,
    opener: Any = None,
    use_cache: bool = True,
) -> str:
    """Safely resolve same-platform short/share social links without following off-domain redirects."""
    if not isinstance(raw_url, str) or not raw_url.strip():
        return raw_url
    cleaned = raw_url.strip()
    if re.search(r"[\s\x00-\x1f\x7f<>\"']", cleaned):
        return raw_url
    parsed = urlsplit(cleaned)
    if parsed.scheme.lower() != "https" or parsed.username or parsed.password:
        return raw_url

    allowed_hosts = _short_link_allowed_hosts(parsed)
    if not allowed_hosts:
        return raw_url

    should_cache = opener is None and use_cache
    if should_cache:
        with _short_url_cache_lock:
            cached = _short_url_cache.get(cleaned)
        if cached:
            return cached

    active_opener = opener or urllib.request.build_opener(_NoRedirectHandler())
    current_url = cleaned

    for _ in range(max(1, int(max_hops))):
        req = urllib.request.Request(
            current_url,
            method="GET",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        location = ""
        html_snippet = ""
        try:
            resp = active_opener.open(req, timeout=timeout)
            try:
                status_code = getattr(resp, "status", 200)
                headers = getattr(resp, "headers", None)
                if status_code in (301, 302, 303, 307, 308) and headers:
                    location = headers.get("Location") or headers.get("location") or ""
                else:
                    final_url = getattr(resp, "geturl", lambda: "")() or ""
                    if final_url and final_url != current_url:
                        location = final_url
                    elif _short_link_allowed_hosts(urlsplit(current_url)) is not None:
                        read_fn = getattr(resp, "read", None)
                        if callable(read_fn):
                            raw_body = read_fn(131072)
                            if isinstance(raw_body, bytes):
                                html_snippet = raw_body.decode("utf-8", errors="ignore")
                            elif isinstance(raw_body, str):
                                html_snippet = raw_body
            finally:
                close_fn = getattr(resp, "close", None)
                if callable(close_fn):
                    close_fn()
        except urllib.error.HTTPError as err:
            if err.code in (301, 302, 303, 307, 308) and err.headers:
                location = err.headers.get("Location") or err.headers.get("location") or ""
            else:
                break
        except Exception:
            break

        if html_snippet and not location:
            extracted = _extract_canonical_from_html(
                html_snippet, current_url, allowed_hosts
            )
            if extracted:
                current_url = extracted
            break

        if not location:
            break

        raw_next = urljoin(current_url, location.strip())
        if re.search(r"[\s\x00-\x1f\x7f<>\"']", raw_next):
            break
        next_parsed = urlsplit(raw_next)
        next_host = (next_parsed.hostname or "").lower()
        next_path_lower = (next_parsed.path or "").lower()

        if (
            next_parsed.scheme.lower() == "https"
            and not next_parsed.username
            and not next_parsed.password
            and next_host in allowed_hosts
            and ("/login" in next_path_lower or "/accounts/login" in next_path_lower)
        ):
            next_param = (parse_qs(next_parsed.query).get("next") or [""])[0].strip()
            safe_next_target = _is_safe_same_platform_url(
                next_param, current_url, allowed_hosts
            )
            if safe_next_target:
                current_url = safe_next_target
                if _short_link_allowed_hosts(urlsplit(current_url)) is None:
                    break
                continue
            break

        safe_redirect = _is_safe_same_platform_url(
            location.strip(), current_url, allowed_hosts
        )
        if not safe_redirect:
            break

        current_url = safe_redirect
        if _short_link_allowed_hosts(urlsplit(current_url)) is None:
            break

    if current_url != cleaned:
        try:
            validate_external_media_url(current_url, resolve_redirects=False)
            if should_cache:
                with _short_url_cache_lock:
                    if len(_short_url_cache) >= _SHORT_URL_CACHE_MAX:
                        _short_url_cache.pop(next(iter(_short_url_cache)), None)
                    _short_url_cache[cleaned] = current_url
            return current_url
        except MediaValidationError:
            return raw_url

    return raw_url


def validate_external_media_url(
    raw_url: str,
    media_type: str | None = None,
    *,
    resolve_redirects: bool = False,
) -> dict[str, Any]:
    """Validate and normalize an external media URL (video, reel, post, image, or audio)."""
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise MediaValidationError(
            "External media URL must be a non-empty string.",
            status_code=400,
            code="INVALID_MEDIA_URL",
        )

    expected_type: str | None = None
    if media_type is not None and str(media_type).strip():
        expected_type = str(media_type).strip().lower()
        if expected_type not in ALLOWED_EXTERNAL_MEDIA_TYPES:
            raise MediaValidationError(
                f"Invalid mediaType '{media_type}'. Must be one of: {', '.join(ALLOWED_EXTERNAL_MEDIA_TYPES)}.",
                status_code=400,
                code="INVALID_MEDIA_TYPE",
            )

    cleaned = raw_url.strip()
    if re.search(r"[\s\x00-\x1f\x7f<>\"']", cleaned):
        raise MediaValidationError(
            "External media URL contains unsafe characters.",
            status_code=400,
            code="UNSAFE_MEDIA_URL",
        )

    candidate_url = resolve_short_social_url(cleaned) if resolve_redirects else cleaned
    parsed = urlsplit(candidate_url)

    if parsed.scheme.lower() != "https":
        raise MediaValidationError(
            "External media URLs must use HTTPS.",
            status_code=400,
            code="INSECURE_MEDIA_URL",
        )

    if parsed.username or parsed.password:
        raise MediaValidationError(
            "External media URLs must not contain embedded credentials.",
            status_code=400,
            code="UNSAFE_MEDIA_URL",
        )

    if _has_traversal_segments(parsed.path):
        raise MediaValidationError(
            "External media URL contains invalid path traversal segments.",
            status_code=400,
            code="UNSAFE_MEDIA_URL",
        )

    host = (parsed.hostname or "").lower()
    if not host:
        raise MediaValidationError(
            "External media URL is missing a valid hostname.",
            status_code=400,
            code="INVALID_MEDIA_URL",
        )

    if host in _YOUTUBE_HOSTS:
        normalized = _parse_youtube_embed(parsed)
    elif host in _VIMEO_HOSTS:
        normalized = _parse_vimeo_embed(parsed)
    elif host in _DAILYMOTION_HOSTS:
        normalized = _parse_dailymotion_embed(parsed)
    elif host in _INSTAGRAM_HOSTS:
        normalized = _parse_instagram_embed(parsed)
    elif host in _FACEBOOK_HOSTS:
        normalized = _parse_facebook_embed(parsed)
    elif host in _TIKTOK_HOSTS:
        normalized = _parse_tiktok_embed(parsed)
    elif host in _X_HOSTS:
        normalized = _parse_x_embed(parsed)
    elif host in _THREADS_HOSTS:
        normalized = _parse_threads_embed(parsed)
    elif host in _LINKEDIN_HOSTS:
        normalized = _parse_linkedin_embed(parsed)
    elif host in _TELEGRAM_HOSTS:
        normalized = _parse_telegram_embed(parsed)
    elif host in _SOUNDCLOUD_HOSTS:
        normalized = _parse_soundcloud_embed(parsed)
    elif host in _SPOTIFY_HOSTS:
        normalized = _parse_spotify_embed(parsed)
    elif host in _GOOGLE_DRIVE_HOSTS:
        normalized = _parse_google_drive_embed(parsed)
    elif host in _GOOGLE_PHOTOS_HOSTS:
        normalized = _parse_google_photos_embed(parsed)
    elif host in _CANVA_HOSTS:
        normalized = _parse_canva_embed(parsed)
    else:
        ext = _get_path_extension(parsed.path)
        if ext == ".svg" or ext in RAW_AV_EXTENSIONS:
            raise MediaValidationError(
                f"Domain '{host}' is not in the external media allowlist.",
                status_code=400,
                code="UNTRUSTED_MEDIA_DOMAIN",
            )
        if ext in EXTERNAL_IMAGE_EXTENSIONS or expected_type == "image":
            normalized = _parse_external_image_url(parsed, candidate_url)
        else:
            raise MediaValidationError(
                f"Domain '{host}' is not in the external media allowlist.",
                status_code=400,
                code="UNTRUSTED_MEDIA_DOMAIN",
            )

    allowed_types = normalized.pop("_allowedTypes", (normalized["mediaType"],))
    if expected_type is not None:
        if expected_type not in allowed_types:
            raise MediaValidationError(
                f"Provider '{normalized['provider']}' serves '{normalized['mediaType']}', not '{expected_type}'.",
                status_code=400,
                code="MEDIA_TYPE_MISMATCH",
            )
        normalized["mediaType"] = expected_type

    probed_dims = None
    if (
        resolve_redirects
        and normalized.get("renderMode") == "iframe"
        and normalized.get("mediaType") in ("video", "reel")
    ):
        if normalized.get("provider") == "facebook" and normalized.get("embedUrl"):
            probed_dims = probe_media_dimensions(normalized["embedUrl"])
            if probed_dims is None:
                probed_dims = probe_media_dimensions(normalized["canonicalUrl"])
        else:
            probed_dims = probe_media_dimensions(normalized["canonicalUrl"])
        if probed_dims is not None:
            normalized["aspectWidth"], normalized["aspectHeight"] = probed_dims

    if (
        normalized.get("mediaType") == "reel"
        and probed_dims is None
        and int(normalized.get("aspectWidth") or 16) > int(normalized.get("aspectHeight") or 9)
    ):
        normalized["aspectWidth"] = 9
        normalized["aspectHeight"] = 16

    return {
        **normalized,
        "originalUrl": cleaned,
        "hostedExternally": True,
    }


def _parse_positive_aspect_dim(raw_val: Any) -> int | None:
    if isinstance(raw_val, bool) or not isinstance(raw_val, int):
        return None
    if 1 <= raw_val <= 10000:
        return raw_val
    return None


def sanitize_external_media_links(
    raw_links: Any,
    *,
    resolve_redirects: bool = False,
) -> list[dict[str, Any]]:
    """Normalize a list of external media links/strings, dropping invalid or untrusted entries."""
    if not raw_links:
        return []
    if not isinstance(raw_links, (list, tuple)):
        raw_links = [raw_links]

    sanitized: list[dict[str, Any]] = []
    for item in raw_links:
        link_id = None
        clean_title = ""
        stored_aw = None
        stored_ah = None
        if isinstance(item, str):
            url_val = item
            requested_type = None
        elif isinstance(item, dict):
            url_val = (
                item.get("url")
                or item.get("canonicalUrl")
                or item.get("canonical_url")
                or item.get("embedUrl")
                or item.get("embed_url")
                or item.get("originalUrl")
                or item.get("original_url")
                or ""
            )
            requested_type = item.get("mediaType") or item.get("media_type")
            stored_aw = _parse_positive_aspect_dim(
                item.get("aspectWidth") if "aspectWidth" in item else item.get("aspect_width")
            )
            stored_ah = _parse_positive_aspect_dim(
                item.get("aspectHeight") if "aspectHeight" in item else item.get("aspect_height")
            )
            raw_id = item.get("id")
            if isinstance(raw_id, int) and not isinstance(raw_id, bool):
                link_id = raw_id
            raw_title = item.get("title")
            if isinstance(raw_title, str) and raw_title.strip():
                stripped_title = re.sub(r"<[^>]*>", " ", raw_title)
                stripped_title = stripped_title.replace("<", " ").replace(">", " ")
                clean_title = " ".join(stripped_title.split())
        else:
            continue

        try:
            needs_redirect = False
            if isinstance(url_val, str) and url_val.strip():
                try:
                    needs_redirect = _short_link_allowed_hosts(urlsplit(url_val.strip())) is not None
                except ValueError:
                    needs_redirect = False
            use_stored_dims = (
                stored_aw is not None
                and stored_ah is not None
                and not needs_redirect
            )
            normalized = validate_external_media_url(
                url_val,
                media_type=requested_type,
                resolve_redirects=False if use_stored_dims else resolve_redirects,
            )
            if use_stored_dims:
                normalized["aspectWidth"] = stored_aw
                normalized["aspectHeight"] = stored_ah
            if link_id is not None:
                normalized["id"] = link_id
            if clean_title:
                normalized["title"] = clean_title
            sanitized.append(normalized)
        except MediaValidationError:
            continue

    return sanitized
