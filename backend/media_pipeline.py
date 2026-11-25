"""OpenCV image ingestion/optimization and external media URL validation utilities."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

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

_YOUTUBE_HOSTS = frozenset({
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtube-nocookie.com",
})
_VIMEO_HOSTS = frozenset({"vimeo.com", "www.vimeo.com", "player.vimeo.com"})
_SOUNDCLOUD_PAGE_HOSTS = frozenset({"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com"})
_SOUNDCLOUD_HOSTS = frozenset({*_SOUNDCLOUD_PAGE_HOSTS, "w.soundcloud.com"})
_GOOGLE_DRIVE_HOSTS = frozenset({"drive.google.com"})

_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_VIMEO_ID_RE = re.compile(r"^\d+$")
_DRIVE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")


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


def _parse_youtube_embed(parsed) -> dict[str, Any]:
    host = (parsed.hostname or "").lower()
    segments = [seg for seg in parsed.path.split("/") if seg]
    video_id = ""

    if host == "youtu.be" and segments:
        video_id = segments[0]
    elif parsed.path == "/watch":
        video_id = (parse_qs(parsed.query).get("v") or [""])[0]
    elif len(segments) >= 2 and segments[0] in ("shorts", "embed", "live"):
        video_id = segments[1]

    if not _YOUTUBE_ID_RE.match(video_id):
        raise MediaValidationError(
            "Invalid YouTube video URL or missing video ID.",
            status_code=400,
            code="INVALID_MEDIA_URL",
        )

    return {
        "mediaType": "video",
        "provider": "youtube",
        "canonicalUrl": f"https://www.youtube.com/watch?v={video_id}",
        "embedUrl": f"https://www.youtube-nocookie.com/embed/{video_id}",
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
            "Invalid Google Drive audio URL or missing file ID.",
            status_code=400,
            code="INVALID_MEDIA_URL",
        )

    return {
        "mediaType": "audio",
        "provider": "google_drive",
        "canonicalUrl": f"https://drive.google.com/file/d/{file_id}/view",
        "embedUrl": f"https://drive.google.com/file/d/{file_id}/preview",
    }


def validate_external_media_url(
    raw_url: str,
    media_type: str | None = None,
) -> dict[str, Any]:
    """Validate and normalize an allowlisted external video/audio URL to a safe HTTPS embed URL."""
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise MediaValidationError(
            "External media URL must be a non-empty string.",
            status_code=400,
            code="INVALID_MEDIA_URL",
        )

    cleaned = raw_url.strip()
    if re.search(r"[\s\x00-\x1f\x7f<>\"']", cleaned):
        raise MediaValidationError(
            "External media URL contains unsafe characters.",
            status_code=400,
            code="UNSAFE_MEDIA_URL",
        )
    parsed = urlsplit(cleaned)

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
    elif host in _SOUNDCLOUD_HOSTS:
        normalized = _parse_soundcloud_embed(parsed)
    elif host in _GOOGLE_DRIVE_HOSTS:
        normalized = _parse_google_drive_embed(parsed)
    else:
        raise MediaValidationError(
            f"Domain '{host}' is not in the external media allowlist.",
            status_code=400,
            code="UNTRUSTED_MEDIA_DOMAIN",
        )

    if media_type is not None and str(media_type).strip():
        expected_type = str(media_type).strip().lower()
        if expected_type not in ("video", "audio"):
            raise MediaValidationError(
                f"Invalid mediaType '{media_type}'. Must be 'video' or 'audio'.",
                status_code=400,
                code="INVALID_MEDIA_TYPE",
            )
        if expected_type != normalized["mediaType"]:
            raise MediaValidationError(
                f"Provider '{normalized['provider']}' serves '{normalized['mediaType']}', not '{expected_type}'.",
                status_code=400,
                code="MEDIA_TYPE_MISMATCH",
            )

    return {
        **normalized,
        "originalUrl": cleaned,
        "hostedExternally": True,
    }


def sanitize_external_media_links(raw_links: Any) -> list[dict[str, Any]]:
    """Normalize a list of external media links/strings, dropping invalid or untrusted entries."""
    if not raw_links:
        return []
    if not isinstance(raw_links, (list, tuple)):
        raw_links = [raw_links]

    sanitized: list[dict[str, Any]] = []
    for item in raw_links:
        link_id = None
        clean_title = ""
        if isinstance(item, str):
            url_val = item
            requested_type = None
        elif isinstance(item, dict):
            url_val = item.get("url") or item.get("embedUrl") or item.get("embed_url") or ""
            requested_type = item.get("mediaType") or item.get("media_type")
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
            normalized = validate_external_media_url(url_val, media_type=requested_type)
            if link_id is not None:
                normalized["id"] = link_id
            if clean_title:
                normalized["title"] = clean_title
            sanitized.append(normalized)
        except MediaValidationError:
            continue

    return sanitized
