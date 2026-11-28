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


@pytest.mark.integration
@pytest.mark.api
class TestFlaskMediaEndpoints:
    """Integration tests for Flask image upload/serving and external media APIs."""

    def test_upload_oversized_jpeg_returns_201_webp_and_serves_cached_asset_without_metadata(
        self, client
    ):
        secret = b"GPS_SECRET_32.5190N_CAMERA_MODEL"
        jpeg_bytes = _encode_jpeg_with_metadata(2000, 1000, marker_text=secret)

        response = client.post(
            "/api/media/images",
            data={"file": (io.BytesIO(jpeg_bytes), "school-event.jpg", "image/jpeg")},
            content_type="multipart/form-data",
        )

        assert response.status_code == 201
        body = response.get_json()
        assert body["format"] == "webp"
        assert body["mimeType"] == "image/webp"
        assert body["width"] == 1280
        assert body["height"] == 640
        assert body["resized"] is True
        assert body["metadataStripped"] is True
        assert body["url"].startswith("/api/media/images/")
        assert body["url"].endswith(".webp")

        fetch_resp = client.get(body["url"])
        assert fetch_resp.status_code == 200
        assert fetch_resp.content_type == "image/webp"
        cache_control = fetch_resp.headers.get("Cache-Control", "")
        assert "public" in cache_control
        assert "immutable" in cache_control
        assert fetch_resp.headers.get("X-Content-Type-Options") == "nosniff"

        served_bytes = fetch_resp.get_data()
        assert secret not in served_bytes
        decoded = cv2.imdecode(np.frombuffer(served_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        assert decoded is not None
        assert decoded.shape == (640, 1280, 3)

    def test_upload_can_export_jpeg_format_and_custom_bounds(self, client):
        png_bytes = _encode_png_with_text_chunk(1200, 900, with_alpha=True)

        response = client.post(
            "/api/media/images",
            data={
                "file": (io.BytesIO(png_bytes), "poster.png", "image/png"),
                "format": "jpeg",
                "max_width": "640",
                "max_height": "640",
                "quality": "75",
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 201
        body = response.get_json()
        assert body["format"] == "jpeg"
        assert body["mimeType"] == "image/jpeg"
        assert body["url"].endswith(".jpg")
        assert body["width"] <= 640
        assert body["height"] <= 640

        fetch_resp = client.get(body["url"])
        assert fetch_resp.status_code == 200
        assert fetch_resp.content_type == "image/jpeg"

    def test_upload_endpoint_rejects_missing_file_raw_av_svg_and_oversized(
        self, client, tmp_path
    ):
        missing = client.post("/api/media/images", data={}, content_type="multipart/form-data")
        assert missing.status_code == 400
        assert missing.get_json()["code"] == "MISSING_FILE"

        mp4 = client.post(
            "/api/media/images",
            data={
                "file": (
                    io.BytesIO(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isom"),
                    "clip.mp4",
                    "video/mp4",
                )
            },
            content_type="multipart/form-data",
        )
        assert mp4.status_code == 415
        assert mp4.get_json()["code"] == "RAW_AV_NOT_ALLOWED"

        mp3 = client.post(
            "/api/media/images",
            data={"file": (io.BytesIO(b"ID3\x04\x00\x00\x00\x00\x00\x00abc"), "audio.mp3", "audio/mpeg")},
            content_type="multipart/form-data",
        )
        assert mp3.status_code == 415
        assert mp3.get_json()["code"] == "RAW_AV_NOT_ALLOWED"

        svg = client.post(
            "/api/media/images",
            data={
                "file": (
                    io.BytesIO(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'),
                    "icon.svg",
                    "image/svg+xml",
                )
            },
            content_type="multipart/form-data",
        )
        assert svg.status_code == 415
        assert svg.get_json()["code"] == "UNSUPPORTED_MEDIA_TYPE"

        small_limit_app = backend_app.create_app({
            "TESTING": True,
            "MEDIA_UPLOAD_DIR": str(tmp_path / "small_uploads"),
            "MAX_IMAGE_UPLOAD_BYTES": 100,
        })
        png_bytes = _encode_png_with_text_chunk(200, 200)
        with small_limit_app.test_client() as small_client:
            too_big = small_client.post(
                "/api/media/images",
                data={"file": (io.BytesIO(png_bytes), "large.png", "image/png")},
                content_type="multipart/form-data",
            )
        assert too_big.status_code == 413
        assert too_big.get_json()["code"] == "FILE_TOO_LARGE"

    def test_serve_image_blocks_path_traversal_and_returns_404_for_missing(self, client):
        traversal = client.get("/api/media/images/..%2Fapp.py")
        assert traversal.status_code in (400, 404)

        invalid_name = client.get("/api/media/images/not-a-valid-name.txt")
        assert invalid_name.status_code == 400
        assert invalid_name.get_json()["code"] == "INVALID_FILENAME"

        missing = client.get("/api/media/images/0123456789abcdef.webp")
        assert missing.status_code == 404

    def test_external_media_endpoint_validates_and_normalizes_or_rejects(self, client):
        yt_resp = client.post(
            "/api/media/external",
            json={"url": "https://youtu.be/dQw4w9WgXcQ"},
        )
        assert yt_resp.status_code == 200
        yt_body = yt_resp.get_json()
        assert yt_body["provider"] == "youtube"
        assert yt_body["mediaType"] == "video"
        assert yt_body["embedUrl"] == "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"
        assert yt_body["hostedExternally"] is True

        sc_resp = client.post(
            "/api/media/external",
            json={"url": "https://soundcloud.com/school/announcement", "mediaType": "audio"},
        )
        assert sc_resp.status_code == 200
        assert sc_resp.get_json()["provider"] == "soundcloud"

        bad_resp = client.post(
            "/api/media/external",
            json={"url": "https://untrusted.example.com/video.mp4"},
        )
        assert bad_resp.status_code == 400
        assert "error" in bad_resp.get_json()
        assert bad_resp.get_json()["code"] == "UNTRUSTED_MEDIA_DOMAIN"

        missing_url = client.post("/api/media/external", json={})
        assert missing_url.status_code == 400
        assert "code" in missing_url.get_json()

    def test_posts_feed_preserves_validated_external_media_links_and_drops_untrusted(
        self, client, post_factory, mock_posts_source
    ):
        mock_posts_source([
            post_factory(
                id=301,
                title="فعالية المدرسة مع فيديو وصوت",
                mediaLinks=[
                    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    {"url": "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQr/view"},
                    "http://evil.com/x.mp4",
                ],
            )
        ])

        response = client.get("/api/posts")
        assert response.status_code == 200

        [post] = response.get_json()
        assert post["id"] == 301
        assert len(post["mediaLinks"]) == 2
        assert post["mediaLinks"][0]["provider"] == "youtube"
        assert post["mediaLinks"][0]["embedUrl"] == "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"
        assert post["mediaLinks"][1]["provider"] == "google_drive"
        assert post["mediaLinks"][1]["embedUrl"] == "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQr/preview"

    @pytest.mark.parametrize(
        "raw_url, explicit_type, expected_type, expected_provider, expected_mode, expected_embed_prefix",
        [
            (
                "https://www.instagram.com/reel/C5AbCdEfGhI/?igsh=xyz",
                None,
                "reel",
                "instagram",
                "iframe",
                "https://www.instagram.com/reel/C5AbCdEfGhI/embed/",
            ),
            (
                "https://www.instagram.com/mahjar_school/reel/C5AbCdEfGhI/",
                None,
                "reel",
                "instagram",
                "iframe",
                "https://www.instagram.com/reel/C5AbCdEfGhI/embed/",
            ),
            (
                "https://www.instagram.com/p/C5AbCdEfGhI/",
                None,
                "post",
                "instagram",
                "iframe",
                "https://www.instagram.com/p/C5AbCdEfGhI/embed/",
            ),
            (
                "https://www.instagram.com/tv/C5AbCdEfGhI/",
                None,
                "video",
                "instagram",
                "iframe",
                "https://www.instagram.com/tv/C5AbCdEfGhI/embed/",
            ),
            (
                "https://www.instagram.com/stories/mahjar.school/34567890123456/",
                None,
                "post",
                "instagram",
                "card",
                "",
            ),
            (
                "https://www.facebook.com/reel/123456789012345",
                None,
                "reel",
                "facebook",
                "iframe",
                "https://www.facebook.com/plugins/video.php?href=",
            ),
            (
                "https://www.facebook.com/watch/?v=9876543210",
                None,
                "video",
                "facebook",
                "iframe",
                "https://www.facebook.com/plugins/video.php?href=",
            ),
            (
                "https://www.facebook.com/mahjar.school/posts/pfbid02XYZ123",
                None,
                "post",
                "facebook",
                "iframe",
                "https://www.facebook.com/plugins/post.php?href=",
            ),
            (
                "https://www.facebook.com/photo/?fbid=1122334455",
                None,
                "post",
                "facebook",
                "iframe",
                "https://www.facebook.com/plugins/post.php?href=",
            ),
            (
                "https://www.facebook.com/groups/123456/videos/987654321/",
                None,
                "video",
                "facebook",
                "iframe",
                "https://www.facebook.com/plugins/video.php?href=",
            ),
            (
                "https://fb.watch/abc123XYZ/",
                None,
                "video",
                "facebook",
                "card",
                "",
            ),
            (
                "https://www.facebook.com/share/r/AbCdEf123/",
                None,
                "reel",
                "facebook",
                "card",
                "",
            ),
            (
                "https://www.facebook.com/share/v/19kinDFpk5/",
                None,
                "video",
                "facebook",
                "card",
                "",
            ),
            (
                "https://www.tiktok.com/@mahjarschool/video/7345678901234567890",
                None,
                "reel",
                "tiktok",
                "iframe",
                "https://www.tiktok.com/embed/v2/7345678901234567890",
            ),
            (
                "https://www.tiktok.com/@mahjarschool/photo/7345678901234567890",
                None,
                "post",
                "tiktok",
                "card",
                "",
            ),
            (
                "https://vm.tiktok.com/ZMrAbCdEf/",
                None,
                "reel",
                "tiktok",
                "card",
                "",
            ),
            (
                "https://x.com/mahjar_school/status/1800123456789012345",
                None,
                "post",
                "x",
                "card",
                "",
            ),
            (
                "https://www.threads.net/@mahjar.school/post/C9AbCdEf123",
                None,
                "post",
                "threads",
                "iframe",
                "https://www.threads.net/@mahjar.school/post/C9AbCdEf123/embed",
            ),
            (
                "https://www.linkedin.com/posts/mahjar-school_activity-12345",
                None,
                "post",
                "linkedin",
                "iframe",
                "https://www.linkedin.com/embed/feed/update/urn:li:activity:12345",
            ),
            (
                "https://t.me/mahjar_parents/42",
                None,
                "post",
                "telegram",
                "iframe",
                "https://t.me/mahjar_parents/42?embed=1",
            ),
            (
                "https://open.spotify.com/episode/4rOoJ6Egrf8K2IrywzwOMk",
                None,
                "audio",
                "spotify",
                "iframe",
                "https://open.spotify.com/embed/episode/4rOoJ6Egrf8K2IrywzwOMk",
            ),
            (
                "https://www.dailymotion.com/video/x8abcde",
                None,
                "video",
                "dailymotion",
                "iframe",
                "https://www.dailymotion.com/embed/video/x8abcde",
            ),
            (
                "https://photos.app.goo.gl/AbCdEfGh123",
                None,
                "image",
                "google_photos",
                "card",
                "",
            ),
            (
                "https://www.canva.com/design/DAGAbCdEfGh/view",
                None,
                "post",
                "canva",
                "iframe",
                "https://www.canva.com/design/DAGAbCdEfGh/view?embed",
            ),
            (
                "https://cdn.example.org/gallery/heritage-day.webp",
                None,
                "image",
                "external_image",
                "image",
                "",
            ),
            (
                "https://images.example.org/render?id=991",
                "image",
                "image",
                "external_image",
                "image",
                "",
            ),
            (
                "https://www.youtube.com/shorts/dQw4w9WgXcQ",
                "reel",
                "reel",
                "youtube",
                "iframe",
                "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
            ),
            (
                "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQr/view",
                "video",
                "video",
                "google_drive",
                "iframe",
                "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQr/preview",
            ),
        ],
    )
    def test_validates_social_reels_posts_external_images_and_audio(
        self,
        raw_url,
        explicit_type,
        expected_type,
        expected_provider,
        expected_mode,
        expected_embed_prefix,
    ):
        result = media_pipeline.validate_external_media_url(raw_url, media_type=explicit_type)
        assert result["mediaType"] == expected_type
        assert result["provider"] == expected_provider
        assert result["renderMode"] == expected_mode
        assert result["hostedExternally"] is True
        if expected_embed_prefix:
            assert result["embedUrl"].startswith(expected_embed_prefix)
        else:
            assert result["embedUrl"] == ""

    @pytest.mark.parametrize(
        "bad_url, media_type, expected_code",
        [
            ("https://127.0.0.1/photo.jpg", None, "UNTRUSTED_MEDIA_DOMAIN"),
            ("https://localhost/banner.png", "image", "UNTRUSTED_MEDIA_DOMAIN"),
            ("https://cdn.example.org/icon.svg", "image", "UNTRUSTED_MEDIA_DOMAIN"),
            ("https://cdn.example.org/clip.mp4", "image", "UNTRUSTED_MEDIA_DOMAIN"),
            ("https://www.instagram.com/unknown/abc", None, "INVALID_MEDIA_URL"),
            (
                "https://www.facebook.com/plugins/video.php?href=https://evil.com/x",
                None,
                "UNTRUSTED_MEDIA_DOMAIN",
            ),
            (
                "https://x.com/mahjar_school/status/1800123456789012345",
                "audio",
                "MEDIA_TYPE_MISMATCH",
            ),
            (
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "podcast",
                "INVALID_MEDIA_TYPE",
            ),
        ],
    )
    def test_rejects_unsafe_private_image_and_invalid_social_urls(
        self, bad_url, media_type, expected_code
    ):
        with pytest.raises(media_pipeline.MediaValidationError) as exc_info:
            media_pipeline.validate_external_media_url(bad_url, media_type=media_type)
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == expected_code

    def test_posts_feed_preserves_card_and_image_media_links_with_empty_embed_url(
        self, client, post_factory, mock_posts_source
    ):
        mock_posts_source([
            post_factory(
                id=302,
                title="تغطية مصورة عبر منصات التواصل",
                mediaLinks=[
                    {
                        "url": "https://x.com/mahjar_school/status/1800123456789012345",
                        "title": "منشور X",
                    },
                    {
                        "url": "https://cdn.example.org/photos/event.webp",
                        "title": "صورة خارجية",
                    },
                    {
                        "url": "https://www.instagram.com/reel/C5AbCdEfGhI/",
                        "title": "رييل الفعالية",
                    },
                ],
            )
        ])

        response = client.get("/api/posts")
        assert response.status_code == 200
        [post] = response.get_json()
        assert len(post["mediaLinks"]) == 3
        assert post["mediaLinks"][0]["provider"] == "x"
        assert post["mediaLinks"][0]["renderMode"] == "card"
        assert post["mediaLinks"][1]["provider"] == "external_image"
        assert post["mediaLinks"][1]["renderMode"] == "image"
        assert post["mediaLinks"][2]["provider"] == "instagram"
        assert post["mediaLinks"][2]["mediaType"] == "reel"
        assert post["mediaLinks"][2]["renderMode"] == "iframe"

    def test_resolve_short_social_url_follows_safe_same_platform_redirects_and_blocks_unsafe(
        self,
    ):
        import urllib.error

        class FakeOpener:
            def __init__(self, mapping):
                self.mapping = mapping
                self.visited = []

            def open(self, req, timeout=3.0):
                url = req.full_url
                self.visited.append(url)
                action = self.mapping.get(url)
                if action is None:
                    raise urllib.error.URLError("not mocked")
                code, loc = action
                if code in (301, 302, 303, 307, 308):
                    raise urllib.error.HTTPError(
                        url, code, "Redirect", {"Location": loc}, None
                    )
                class _OKResp:
                    status = code
                    headers = {}
                    def geturl(self):
                        return url
                    def close(self):
                        pass
                return _OKResp()

        fb_opener = FakeOpener({
            "https://www.facebook.com/share/v/19kinDFpk5/": (
                302,
                "https://www.facebook.com/mahjar.school/videos/987654321/",
            ),
            "https://www.facebook.com/mahjar.school/videos/987654321/": (200, ""),
        })
        assert (
            media_pipeline.resolve_short_social_url(
                "https://www.facebook.com/share/v/19kinDFpk5/", opener=fb_opener
            )
            == "https://www.facebook.com/mahjar.school/videos/987654321/"
        )

        tt_opener = FakeOpener({
            "https://vm.tiktok.com/ZMrAbCdEf/": (
                301,
                "https://www.tiktok.com/@mahjar/video/7345678901234567890",
            ),
            "https://www.tiktok.com/@mahjar/video/7345678901234567890": (200, ""),
        })
        assert (
            media_pipeline.resolve_short_social_url(
                "https://vm.tiktok.com/ZMrAbCdEf/", opener=tt_opener
            )
            == "https://www.tiktok.com/@mahjar/video/7345678901234567890"
        )

        # Off-domain / insecure redirect must NOT be followed and falls back safely
        evil_opener = FakeOpener({
            "https://www.facebook.com/share/v/19kinDFpk5/": (
                302,
                "https://evil.example.com/phish",
            ),
        })
        assert (
            media_pipeline.resolve_short_social_url(
                "https://www.facebook.com/share/v/19kinDFpk5/", opener=evil_opener
            )
            == "https://www.facebook.com/share/v/19kinDFpk5/"
        )
        assert evil_opener.visited == ["https://www.facebook.com/share/v/19kinDFpk5/"]

        # Login wall without next param falls back safely to original share URL
        login_opener = FakeOpener({
            "https://www.facebook.com/share/v/19kinDFpk5/": (
                302,
                "https://www.facebook.com/login/?locale=ar_AR",
            ),
        })
        assert (
            media_pipeline.resolve_short_social_url(
                "https://www.facebook.com/share/v/19kinDFpk5/", opener=login_opener
            )
            == "https://www.facebook.com/share/v/19kinDFpk5/"
        )

        # Login wall WITH safe same-platform ?next= extracts the true video URL
        login_next_opener = FakeOpener({
            "https://www.facebook.com/share/v/19kinDFpk5/": (
                302,
                "https://www.facebook.com/login/?next=https%3A%2F%2Fwww.facebook.com%2Fwatch%2F%3Fv%3D987654321",
            ),
        })
        assert (
            media_pipeline.resolve_short_social_url(
                "https://www.facebook.com/share/v/19kinDFpk5/", opener=login_next_opener
            )
            == "https://www.facebook.com/watch/?v=987654321"
        )

        # 200 OK HTML page with og:url or video_id extracts canonical Facebook URL
        class FakeHtmlOpener:
            def __init__(self, body: bytes):
                self.body = body

            def open(self, req, timeout=4.0):
                body = self.body
                class _HtmlResp:
                    status = 200
                    headers = {}
                    def geturl(self):
                        return req.full_url
                    def read(self, _n=-1):
                        return body
                    def close(self):
                        pass
                return _HtmlResp()

        og_html = b'<html><head><meta property="og:url" content="https://www.facebook.com/mahjar.school/videos/987654321/"></head></html>'
        assert (
            media_pipeline.resolve_short_social_url(
                "https://www.facebook.com/share/v/19kinDFpk5/",
                opener=FakeHtmlOpener(og_html),
            )
            == "https://www.facebook.com/mahjar.school/videos/987654321/"
        )

        vid_html = b'<script>{"video_id":"987654321"}</script>'
        assert (
            media_pipeline.resolve_short_social_url(
                "https://www.facebook.com/share/v/19kinDFpk5/",
                opener=FakeHtmlOpener(vid_html),
            )
            == "https://www.facebook.com/watch/?v=987654321"
        )

        # sanitize_external_media_links preserves resolved canonicalUrl over originalUrl
        sanitized = media_pipeline.sanitize_external_media_links([
            {
                "canonicalUrl": "https://www.facebook.com/watch/?v=987654321",
                "originalUrl": "https://www.facebook.com/share/v/19kinDFpk5/",
                "aspectWidth": 720,
                "aspectHeight": 1280,
            }
        ])
        assert len(sanitized) == 1
        assert sanitized[0]["renderMode"] == "iframe"
        assert "plugins/video.php" in sanitized[0]["embedUrl"]
        assert sanitized[0]["aspectWidth"] == 720
        assert sanitized[0]["aspectHeight"] == 1280

        # Default aspect ratios on YouTube Shorts vs standard YouTube
        yt_short = media_pipeline.validate_external_media_url(
            "https://www.youtube.com/shorts/dQw4w9WgXcQ"
        )
        assert (yt_short["aspectWidth"], yt_short["aspectHeight"]) == (9, 16)
        yt_std = media_pipeline.validate_external_media_url(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )
        assert (yt_std["aspectWidth"], yt_std["aspectHeight"]) == (16, 9)

        # probe_media_dimensions extracts og:video and Facebook original_width/height
        portrait_og_html = (
            b'<html><head>'
            b'<meta property="og:video:width" content="720">'
            b'<meta property="og:video:height" content="1280">'
            b'</head></html>'
        )
        assert (
            media_pipeline.probe_media_dimensions(
                "https://www.facebook.com/watch/?v=987654321",
                opener=FakeHtmlOpener(portrait_og_html),
            )
            == (720, 1280)
        )

        fb_json_html = b'<script>{"original_width":540,"original_height":960}</script>'
        assert (
            media_pipeline.probe_media_dimensions(
                "https://www.facebook.com/watch/?v=987654321",
                opener=FakeHtmlOpener(fb_json_html),
            )
            == (540, 960)
        )

        # Facebook plugins/video.php real HTML (data-video-width/height + padding-bottom + sprite widths)
        plugin_landscape_html = (
            b'<div class="_53j5 _37u6 _9kkd" style="padding-bottom:56.20%;" tabindex="0">'
            b'<video height="281" width="500" preload="auto" class="_ox1 _21y0" '
            b'data-video-width="500" data-video-height="281" id="u_0_1"></video>'
            b'</div><script>{"width":12,"height":12}</script>'
        )
        assert (
            media_pipeline.probe_media_dimensions(
                "https://www.facebook.com/plugins/video.php?href=https%3A%2F%2Fwww.facebook.com%2Freel%2F1391452396433188&show_text=false",
                opener=FakeHtmlOpener(plugin_landscape_html),
            )
            == (500, 281)
        )

        plugin_portrait_html = (
            b'<div class="_53j5 _37u6 _9kkd" style="padding-bottom:134.40%;" tabindex="0">'
            b'<video height="672" width="500" preload="auto" class="_ox1 _21y0" '
            b'data-video-width="500" data-video-height="672" id="u_0_2"></video>'
            b'</div><script>{"width":12,"height":12}</script>'
        )
        assert (
            media_pipeline.probe_media_dimensions(
                "https://www.facebook.com/plugins/video.php?href=https%3A%2F%2Fwww.facebook.com%2Freel%2F970468269089750&show_text=false",
                opener=FakeHtmlOpener(plugin_portrait_html),
            )
            == (500, 672)
        )

        padding_only_html = (
            b'<div class="_53j5" style="padding-bottom:56.20%;"></div>'
            b'<script>{"width":200,"height":200}</script>'
        )
        assert (
            media_pipeline.probe_media_dimensions(
                "https://www.facebook.com/plugins/video.php?href=https%3A%2F%2Fwww.facebook.com%2Freel%2F1391452396433188&show_text=false",
                opener=FakeHtmlOpener(padding_only_html),
            )
            == (1000, 562)
        )

        video_wh_html = b'<script>{"video_width":1280,"video_height":720}</script>'
        assert (
            media_pipeline.probe_media_dimensions(
                "https://www.facebook.com/watch/?v=555666777",
                opener=FakeHtmlOpener(video_wh_html),
            )
            == (1280, 720)
        )

        # Landscape Facebook /reel/ preserves landscape dimensions when probed via plugins/video.php
        orig_probe = media_pipeline.probe_media_dimensions
        try:
            media_pipeline.probe_media_dimensions = (
                lambda raw_u, **_kw: (1280, 720) if "plugins/video.php" in raw_u else None
            )
            landscape_reel = media_pipeline.validate_external_media_url(
                "https://www.facebook.com/reel/1391452396433188",
                resolve_redirects=True,
            )
            assert landscape_reel["mediaType"] == "reel"
            assert (landscape_reel["aspectWidth"], landscape_reel["aspectHeight"]) == (1280, 720)
        finally:
            media_pipeline.probe_media_dimensions = orig_probe

        # /share/p/ HTML containing JSON-escaped permalink.php resolves cleanly
        share_post_html = (
            b'<script>{"share_url":"https:\\/\\/www.facebook.com\\/permalink.php?story_fbid=pfbid02XYZ123&id=61578863263906"}</script>'
        )
        assert (
            media_pipeline.resolve_short_social_url(
                "https://www.facebook.com/share/p/18AbCdEfGh/",
                opener=FakeHtmlOpener(share_post_html),
            )
            == "https://www.facebook.com/permalink.php?story_fbid=pfbid02XYZ123&id=61578863263906"
        )

        # sanitize_external_media_links(..., resolve_redirects=True) preserves stored dimensions
        # without re-probing direct canonical URLs
        sanitized_stored = media_pipeline.sanitize_external_media_links(
            [
                {
                    "canonicalUrl": "https://www.facebook.com/reel/1391452396433188",
                    "originalUrl": "https://www.facebook.com/reel/1391452396433188",
                    "mediaType": "reel",
                    "aspectWidth": 1280,
                    "aspectHeight": 720,
                }
            ],
            resolve_redirects=True,
        )
        assert len(sanitized_stored) == 1
        assert (sanitized_stored[0]["aspectWidth"], sanitized_stored[0]["aspectHeight"]) == (1280, 720)
