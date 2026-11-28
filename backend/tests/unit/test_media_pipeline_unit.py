import io
import struct
import zlib

import cv2
import numpy as np
import pytest

import app as backend_app
import media_pipeline


def _make_bgr_image(width: int, height: int) -> np.ndarray:
    """Create a synthetic textured BGR image for deterministic OpenCV tests."""
    x = np.linspace(0, 255, width, dtype=np.uint8)
    y = np.linspace(0, 255, height, dtype=np.uint8)[:, None]
    blue = np.broadcast_to(x, (height, width))
    green = np.broadcast_to(y, (height, width))
    red = ((blue.astype(np.uint16) + green.astype(np.uint16)) // 2).astype(np.uint8)
    return np.stack([blue, green, red], axis=2)


def _encode_jpeg_with_metadata(
    width: int,
    height: int,
    marker_text: bytes = b"GPS_SECRET_32.5190N_CAMERA_MODEL",
) -> bytes:
    """Encode a JPEG image and inject valid APP1 (EXIF) and COM metadata segments."""
    img = _make_bgr_image(width, height)
    ok, encoded = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    assert ok
    raw = encoded.tobytes()
    assert raw.startswith(b"\xff\xd8")

    app1_payload = b"Exif\x00\x00" + marker_text
    app1_segment = b"\xff\xe1" + struct.pack(">H", len(app1_payload) + 2) + app1_payload
    com_segment = b"\xff\xfe" + struct.pack(">H", len(marker_text) + 2) + marker_text

    return raw[:2] + app1_segment + com_segment + raw[2:]


def _encode_png_with_text_chunk(
    width: int,
    height: int,
    with_alpha: bool = False,
    secret_text: bytes = b"Author\x00SECRET_PNG_METADATA",
) -> bytes:
    """Encode a PNG image (BGR or BGRA) and inject a CRC32-signed tEXt chunk."""
    bgr = _make_bgr_image(width, height)
    if with_alpha:
        alpha = np.full((height, width), 255, dtype=np.uint8)
        # Transparent top-left region to test white-background compositing for JPEG
        alpha[: max(1, height // 4), : max(1, width // 4)] = 0
        img = np.dstack([bgr, alpha])
    else:
        img = bgr

    ok, encoded = cv2.imencode(".png", img)
    assert ok
    raw = encoded.tobytes()

    chunk_type = b"tEXt"
    chunk_crc = zlib.crc32(chunk_type + secret_text) & 0xFFFFFFFF
    text_chunk = (
        struct.pack(">I", len(secret_text))
        + chunk_type
        + secret_text
        + struct.pack(">I", chunk_crc)
    )

    iend_marker = b"\x00\x00\x00\x00IEND\xae\x42\x60\x82"
    assert raw.endswith(iend_marker)
    return raw[: -len(iend_marker)] + text_chunk + iend_marker


def _encode_bmp(width: int, height: int) -> bytes:
    """Encode a synthetic image as uncompressed BMP bytes."""
    ok, encoded = cv2.imencode(".bmp", _make_bgr_image(width, height))
    assert ok
    return encoded.tobytes()


def _encode_webp(width: int, height: int) -> bytes:
    """Encode a synthetic image as WebP bytes."""
    ok, encoded = cv2.imencode(".webp", _make_bgr_image(width, height), [cv2.IMWRITE_WEBP_QUALITY, 95])
    assert ok
    return encoded.tobytes()


@pytest.mark.unit
class TestOpenCVImageOptimizationPipeline:
    """Unit tests for OpenCV image validation, resizing, metadata stripping, and encoding."""

    @pytest.mark.parametrize(
        "filename, content_type, builder, expect_smaller",
        [
            ("photo.jpg", "image/jpeg", lambda: _encode_jpeg_with_metadata(640, 480), True),
            ("flyer.png", "image/png", lambda: _encode_png_with_text_chunk(640, 480), True),
            ("banner.webp", "image/webp", lambda: _encode_webp(640, 480), False),
            ("scan.bmp", "image/bmp", lambda: _encode_bmp(640, 480), True),
        ],
    )
    def test_optimizes_valid_jpeg_png_webp_bmp_to_default_webp(
        self, filename, content_type, builder, expect_smaller
    ):
        raw_bytes = builder()
        result = media_pipeline.optimize_image(
            raw_bytes,
            filename=filename,
            content_type=content_type,
        )

        assert result["format"] == "webp"
        assert result["mimeType"] == "image/webp"
        assert result["extension"] == ".webp"
        assert result["filename"].endswith(".webp")
        assert result["metadataStripped"] is True
        assert result["originalBytes"] == len(raw_bytes)
        assert result["optimizedBytes"] == len(result["data"])
        assert result["data"][:4] == b"RIFF" and result["data"][8:12] == b"WEBP"

        decoded = cv2.imdecode(np.frombuffer(result["data"], dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        assert decoded is not None
        assert decoded.shape[1] == result["width"]
        assert decoded.shape[0] == result["height"]

        if expect_smaller:
            assert result["optimizedBytes"] < result["originalBytes"]

    def test_exports_compressed_jpeg_and_composites_alpha_onto_white(self):
        bgra_png = _encode_png_with_text_chunk(200, 200, with_alpha=True)

        for fmt in ("jpeg", "jpg"):
            result = media_pipeline.optimize_image(
                bgra_png,
                filename="logo.png",
                content_type="image/png",
                output_format=fmt,
                quality=80,
            )

            assert result["format"] == "jpeg"
            assert result["mimeType"] == "image/jpeg"
            assert result["extension"] == ".jpg"
            assert result["filename"].endswith(".jpg")
            assert result["data"].startswith(b"\xff\xd8\xff")

            decoded = cv2.imdecode(np.frombuffer(result["data"], dtype=np.uint8), cv2.IMREAD_UNCHANGED)
            assert decoded is not None
            assert decoded.shape == (200, 200, 3)
            # Top-left was transparent (0, 0, 0, 0) -> should be composited onto white (~255, 255, 255)
            top_left_pixel = decoded[2, 2]
            assert all(channel >= 245 for channel in top_left_pixel)

    def test_resizes_oversized_landscape_and_portrait_preserving_aspect_ratio(self):
        landscape_bytes = _encode_jpeg_with_metadata(2400, 1600)
        landscape = media_pipeline.optimize_image(
            landscape_bytes,
            filename="landscape.jpg",
            content_type="image/jpeg",
            max_width=1280,
            max_height=1280,
        )
        assert landscape["originalWidth"] == 2400
        assert landscape["originalHeight"] == 1600
        assert landscape["width"] == 1280
        assert landscape["height"] == 853
        assert landscape["resized"] is True

        portrait_bytes = _encode_jpeg_with_metadata(1600, 2400)
        portrait = media_pipeline.optimize_image(
            portrait_bytes,
            filename="portrait.jpg",
            content_type="image/jpeg",
            max_width=1280,
            max_height=1280,
        )
        assert portrait["originalWidth"] == 1600
        assert portrait["originalHeight"] == 2400
        assert portrait["width"] == 853
        assert portrait["height"] == 1280
        assert portrait["resized"] is True

    def test_does_not_upscale_images_within_bounds(self):
        small_bytes = _encode_png_with_text_chunk(320, 240)
        result = media_pipeline.optimize_image(
            small_bytes,
            filename="small.png",
            content_type="image/png",
            max_width=1280,
            max_height=1280,
        )
        assert result["originalWidth"] == 320
        assert result["originalHeight"] == 240
        assert result["width"] == 320
        assert result["height"] == 240
        assert result["resized"] is False

    def test_strips_exif_comment_and_png_text_metadata(self):
        jpeg_secret = b"GPS_SECRET_32.5190N_CAMERA_MODEL"
        jpeg_with_meta = _encode_jpeg_with_metadata(400, 300, marker_text=jpeg_secret)
        assert jpeg_secret in jpeg_with_meta

        for fmt in ("webp", "jpeg"):
            res = media_pipeline.optimize_image(
                jpeg_with_meta,
                filename="camera.jpg",
                content_type="image/jpeg",
                output_format=fmt,
            )
            assert jpeg_secret not in res["data"]
            assert res["metadataStripped"] is True

        png_secret = b"Author\x00SECRET_PNG_METADATA"
        png_with_meta = _encode_png_with_text_chunk(400, 300, secret_text=png_secret)
        assert png_secret in png_with_meta

        for fmt in ("webp", "jpeg"):
            res = media_pipeline.optimize_image(
                png_with_meta,
                filename="poster.png",
                content_type="image/png",
                output_format=fmt,
            )
            assert b"SECRET_PNG_METADATA" not in res["data"]
            assert res["metadataStripped"] is True

    @pytest.mark.parametrize(
        "payload, filename, content_type",
        [
            (b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2", "video.mp4", "video/mp4"),
            # Spoofed extension/MIME: MP4 magic bytes disguised as .jpg
            (b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom", "fake.jpg", "image/jpeg"),
            (b"ID3\x04\x00\x00\x00\x00\x00\x00audio-frames", "voice.mp3", "audio/mpeg"),
            (b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00", "clip.wav", "audio/wav"),
            (b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00", "note.ogg", "audio/ogg"),
            (b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01webm", "lecture.webm", "video/webm"),
            (b"random-bytes", "meeting.mp4", "application/octet-stream"),
            (b"random-bytes", "song.m4a", "audio/mp4"),
        ],
    )
    def test_rejects_raw_audio_and_video_uploads_by_mime_extension_and_magic_bytes(
        self, payload, filename, content_type
    ):
        with pytest.raises(media_pipeline.MediaValidationError) as exc_info:
            media_pipeline.optimize_image(
                payload,
                filename=filename,
                content_type=content_type,
            )

        assert exc_info.value.status_code == 415
        assert exc_info.value.code == "RAW_AV_NOT_ALLOWED"

    def test_rejects_empty_oversized_corrupted_svg_and_invalid_params(self):
        # Empty payload
        with pytest.raises(media_pipeline.MediaValidationError) as empty_exc:
            media_pipeline.optimize_image(b"", filename="empty.jpg", content_type="image/jpeg")
        assert empty_exc.value.status_code == 400
        assert empty_exc.value.code == "EMPTY_FILE"

        # Exceeds max_bytes
        valid_png = _encode_png_with_text_chunk(100, 100)
        with pytest.raises(media_pipeline.MediaValidationError) as big_exc:
            media_pipeline.optimize_image(
                valid_png,
                filename="big.png",
                content_type="image/png",
                max_bytes=128,
            )
        assert big_exc.value.status_code == 413
        assert big_exc.value.code == "FILE_TOO_LARGE"

        # SVG (XSS vector) and plain text
        with pytest.raises(media_pipeline.MediaValidationError) as svg_exc:
            media_pipeline.optimize_image(
                b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"></svg>',
                filename="badge.svg",
                content_type="image/svg+xml",
            )
        assert svg_exc.value.status_code == 415
        assert svg_exc.value.code == "UNSUPPORTED_MEDIA_TYPE"

        with pytest.raises(media_pipeline.MediaValidationError) as txt_exc:
            media_pipeline.optimize_image(
                b"not an image",
                filename="notes.txt",
                content_type="text/plain",
            )
        assert txt_exc.value.status_code == 415
        assert txt_exc.value.code == "UNSUPPORTED_MEDIA_TYPE"

        # Corrupted JPEG bytes
        with pytest.raises(media_pipeline.MediaValidationError) as corrupt_exc:
            media_pipeline.optimize_image(
                b"\xff\xd8\xff\x00corrupt-jpeg-payload",
                filename="broken.jpg",
                content_type="image/jpeg",
            )
        assert corrupt_exc.value.status_code == 400
        assert corrupt_exc.value.code == "INVALID_IMAGE_DATA"

        # Unsupported output format
        with pytest.raises(media_pipeline.MediaValidationError) as fmt_exc:
            media_pipeline.optimize_image(
                valid_png,
                filename="ok.png",
                content_type="image/png",
                output_format="gif",
            )
        assert fmt_exc.value.status_code == 400
        assert fmt_exc.value.code == "UNSUPPORTED_OUTPUT_FORMAT"

        # Invalid quality values
        for bad_quality in (0, 101, "abc"):
            with pytest.raises(media_pipeline.MediaValidationError) as q_exc:
                media_pipeline.optimize_image(
                    valid_png,
                    filename="ok.png",
                    content_type="image/png",
                    quality=bad_quality,
                )
            assert q_exc.value.status_code == 400
            assert q_exc.value.code == "INVALID_QUALITY"


@pytest.mark.unit
class TestExternalMediaUrlValidation:
    """Unit tests for allowlisted external video/audio embed normalization."""

    @pytest.mark.parametrize(
        "raw_url, expected_type, expected_provider, expected_embed",
        [
            (
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=share",
                "video",
                "youtube",
                "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
            ),
            (
                "https://youtu.be/dQw4w9WgXcQ?t=15",
                "video",
                "youtube",
                "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
            ),
            (
                "https://www.youtube.com/shorts/dQw4w9WgXcQ",
                "video",
                "youtube",
                "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
            ),
            (
                "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
                "video",
                "youtube",
                "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
            ),
            (
                "https://vimeo.com/123456789",
                "video",
                "vimeo",
                "https://player.vimeo.com/video/123456789",
            ),
            (
                "https://player.vimeo.com/video/123456789",
                "video",
                "vimeo",
                "https://player.vimeo.com/video/123456789",
            ),
            (
                "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQr/view?usp=sharing",
                "audio",
                "google_drive",
                "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQr/preview",
            ),
            (
                "https://drive.google.com/open?id=1AbCdEfGhIjKlMnOpQr",
                "audio",
                "google_drive",
                "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQr/preview",
            ),
        ],
    )
    def test_validates_and_normalizes_allowlisted_external_video_and_audio_urls(
        self, raw_url, expected_type, expected_provider, expected_embed
    ):
        result = media_pipeline.validate_external_media_url(raw_url)
        assert result["mediaType"] == expected_type
        assert result["provider"] == expected_provider
        assert result["embedUrl"] == expected_embed
        assert result["hostedExternally"] is True

        sc = media_pipeline.validate_external_media_url(
            "https://soundcloud.com/school/morning-announcement"
        )
        assert sc["mediaType"] == "audio"
        assert sc["provider"] == "soundcloud"
        assert sc["embedUrl"].startswith("https://w.soundcloud.com/player/?url=")
        assert sc["hostedExternally"] is True

    @pytest.mark.parametrize(
        "bad_url, media_type, expected_code",
        [
            ("http://www.youtube.com/watch?v=dQw4w9WgXcQ", None, "INSECURE_MEDIA_URL"),
            ("javascript:alert(1)", None, "INSECURE_MEDIA_URL"),
            ("https://evil.example.com/video.mp4", None, "UNTRUSTED_MEDIA_DOMAIN"),
            ("https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ", None, "UNTRUSTED_MEDIA_DOMAIN"),
            ("https://user:pass@youtube.com/watch?v=dQw4w9WgXcQ", None, "UNSAFE_MEDIA_URL"),
            ("https://soundcloud.com/school/track", "video", "MEDIA_TYPE_MISMATCH"),
            ("https://w.soundcloud.com/player/?url=https://evil.com/x", None, "UNTRUSTED_MEDIA_DOMAIN"),
        ],
    )
    def test_rejects_untrusted_non_https_xss_and_mismatched_external_media_urls(
        self, bad_url, media_type, expected_code
    ):
        with pytest.raises(media_pipeline.MediaValidationError) as exc_info:
            media_pipeline.validate_external_media_url(bad_url, media_type=media_type)

        assert exc_info.value.status_code == 400
        assert exc_info.value.code == expected_code
