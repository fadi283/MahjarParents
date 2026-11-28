import pytest

import post_preview


SAMPLE_INDEX_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">

<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
  <meta name="theme-color" content="#0f766e" />
  <meta name="description"
    content="المنصة الرقمية للتواصل المجتمعي – لجنة أولياء أمور الطلاب في مدرسة المحجر الابتدائية: الإعلانات، الفعاليات، والنماذج التفاعلية للأهالي." />
  <meta property="og:type" content="website" />
  <meta property="og:locale" content="ar_AR" />
  <meta property="og:site_name" content="لجنة أولياء أمور الطلاب - مدرسة المحجر الابتدائية" />
  <meta property="og:title" content="لجنة أولياء أمور الطلاب - مدرسة المحجر الابتدائية" />
  <meta property="og:description"
    content="تابعوا أحدث إعلانات وفعاليات مدرسة المحجر الابتدائية، وشاركوا آراءكم وسجّلوا في الأنشطة المدرسية بسهولة." />
  <meta property="og:image" content="/logo.jpg" />
  <meta name="twitter:card" content="summary" />
  <meta name="twitter:title" content="لجنة أولياء أمور الطلاب - مدرسة المحجر الابتدائية" />
  <meta name="twitter:description"
    content="المنصة الرقمية للتواصل المجتمعي – لجنة أولياء أمور الطلاب في مدرسة المحجر الابتدائية." />
  <meta name="twitter:image" content="/logo.jpg" />
  <link rel="icon" type="image/jpeg" href="/logo.jpg" />
  <title>لجنة أولياء أمور الطلاب - مدرسة المحجر الابتدائية</title>
</head>

<body>
  <div id="root"></div>
  <script type="module" src="/src/main.jsx"></script>
</body>

</html>
"""


@pytest.mark.unit
class TestPostPreviewHtmlBuilder:
    """Unit tests for post-specific Open Graph / Twitter metadata injection."""

    def test_injects_post_specific_og_twitter_and_canonical_tags_replacing_multiline_defaults(self):
        post = {
            "id": 102,
            "title": "يوم التراث والهوية في مدرسة المحجر الابتدائية",
            "summary": "دعوة لأهالي الطلاب للمشاركة في فعاليات يوم التراث السنوي.",
            "publishedAt": "2026-11-24T10:30:00Z",
            "imageUrl": "/api/media/images/abc123def456.webp",
        }

        rendered = post_preview.build_post_preview_html(
            SAMPLE_INDEX_HTML,
            post,
            site_origin="https://mahjar.example.org",
            media_origin="https://api.mahjar.example.org",
        )

        # Preserves document skeleton and site-level attributes
        assert '<html lang="ar" dir="rtl">' in rendered
        assert '<div id="root"></div>' in rendered
        assert '<script type="module" src="/src/main.jsx"></script>' in rendered
        assert 'property="og:locale" content="ar_AR"' in rendered
        assert f'property="og:site_name" content="{post_preview.SITE_NAME}"' in rendered

        # Replaces title, description, OG, Twitter, canonical without duplicates
        assert f"<title>{post['title']} | {post_preview.SITE_NAME}</title>" in rendered
        assert rendered.count("<title>") == 1
        assert rendered.count('name="description"') == 1
        assert rendered.count('property="og:title"') == 1
        assert rendered.count('property="og:description"') == 1
        assert rendered.count('property="og:url"') == 1
        assert rendered.count('property="og:image"') == 1
        assert rendered.count('property="og:type"') == 1
        assert rendered.count('name="twitter:card"') == 1
        assert rendered.count('name="twitter:title"') == 1
        assert rendered.count('name="twitter:description"') == 1
        assert rendered.count('name="twitter:image"') == 1
        assert rendered.count('rel="canonical"') == 1

        assert 'property="og:type" content="article"' in rendered
        assert f'property="og:title" content="{post["title"]}"' in rendered
        assert f'property="og:description" content="{post["summary"]}"' in rendered
        assert 'property="og:url" content="https://mahjar.example.org/posts/102"' in rendered
        assert 'rel="canonical" href="https://mahjar.example.org/posts/102"' in rendered
        assert 'property="og:image" content="https://api.mahjar.example.org/api/media/images/abc123def456.webp?format=jpeg"' in rendered
        assert 'property="og:image:secure_url" content="https://api.mahjar.example.org/api/media/images/abc123def456.webp?format=jpeg"' in rendered
        assert 'property="og:image:type" content="image/jpeg"' in rendered
        assert f'property="og:image:alt" content="{post["title"]}"' in rendered
        assert 'property="article:published_time" content="2026-11-24T10:30:00Z"' in rendered
        assert 'name="twitter:card" content="summary_large_image"' in rendered
        assert 'name="twitter:image" content="https://api.mahjar.example.org/api/media/images/abc123def456.webp?format=jpeg"' in rendered
        assert f'name="twitter:image:alt" content="{post["title"]}"' in rendered
        assert "تابعوا أحدث إعلانات وفعاليات" not in rendered

    def test_falls_back_to_external_image_youtube_thumbnail_or_site_logo(self):
        external_img_post = {
            "id": 7,
            "title": "معرض الكتاب المدرسي",
            "content": "تفاصيل المعرض السنوي للكتاب.",
            "imageUrl": "",
            "mediaLinks": [
                {"mediaType": "video", "canonicalUrl": "https://youtu.be/dQw4w9WgXcQ"},
                {"mediaType": "image", "canonicalUrl": "https://cdn.example.org/book-fair.jpg"},
            ],
        }
        rendered_ext = post_preview.build_post_preview_html(
            SAMPLE_INDEX_HTML,
            external_img_post,
            site_origin="https://mahjar.example.org",
        )
        assert 'property="og:image" content="https://cdn.example.org/book-fair.jpg"' in rendered_ext
        assert 'property="og:image:type" content="image/jpeg"' in rendered_ext
        assert 'name="twitter:card" content="summary_large_image"' in rendered_ext
        assert 'property="og:description" content="تفاصيل المعرض السنوي للكتاب."' in rendered_ext

        yt_only_post = {
            "id": 17,
            "title": "فيديو حفل التخرج",
            "summary": "شاهدوا مقتطفات من حفل التخرج.",
            "imageUrl": "",
            "mediaLinks": [
                {"mediaType": "video", "canonicalUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            ],
        }
        rendered_yt = post_preview.build_post_preview_html(
            SAMPLE_INDEX_HTML,
            yt_only_post,
            site_origin="https://mahjar.example.org",
        )
        assert 'property="og:image" content="https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"' in rendered_yt
        assert 'property="og:image:secure_url" content="https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"' in rendered_yt
        assert 'property="og:image:type" content="image/jpeg"' in rendered_yt
        assert 'property="og:image:width" content="480"' in rendered_yt
        assert 'property="og:image:height" content="360"' in rendered_yt
        assert 'name="twitter:card" content="summary_large_image"' in rendered_yt

        invalid_yt_post = {
            "id": 18,
            "title": "رابط فيديو غير صالح",
            "summary": "اختبار.",
            "mediaLinks": [
                {"mediaType": "video", "canonicalUrl": "https://youtu.be/short"},
            ],
        }
        rendered_invalid_yt = post_preview.build_post_preview_html(
            SAMPLE_INDEX_HTML,
            invalid_yt_post,
            site_origin="https://mahjar.example.org",
        )
        assert 'property="og:image" content="https://mahjar.example.org/logo.jpg"' in rendered_invalid_yt

        no_img_post = {
            "id": 8,
            "title": "تعميم هام للأهالي",
            "summary": "يرجى الانتباه لمواعيد الدوام.",
            "imageUrl": "",
        }
        rendered_logo = post_preview.build_post_preview_html(
            SAMPLE_INDEX_HTML,
            no_img_post,
            site_origin="https://mahjar.example.org",
        )
        assert 'property="og:image" content="https://mahjar.example.org/logo.jpg"' in rendered_logo
        assert 'name="twitter:image" content="https://mahjar.example.org/logo.jpg"' in rendered_logo
        assert 'name="twitter:card" content="summary"' in rendered_logo
        assert "article:published_time" not in rendered_logo

    def test_escapes_xss_in_title_and_summary_and_rejects_unsafe_image_urls(self):
        xss_post = {
            "id": 99,
            "title": 'إعلان "هام" <script>alert(1)</script> & أولياء الأمور',
            "summary": '<img src=x onerror="alert(1)"> تفاصيل \'الفعالية\'',
            "imageUrl": "javascript:alert(1)",
            "mediaLinks": [
                {"mediaType": "image", "canonicalUrl": "https://user:pass@evil.example/img.jpg"},
            ],
        }

        rendered = post_preview.build_post_preview_html(
            SAMPLE_INDEX_HTML,
            xss_post,
            site_origin="https://mahjar.example.org",
        )

        assert "<script>alert(1)</script>" not in rendered
        assert "<img src=x" not in rendered
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
        assert "&quot;هام&quot;" in rendered
        assert "javascript:alert" not in rendered
        assert "user:pass@evil.example" not in rendered
        assert 'property="og:image" content="https://mahjar.example.org/logo.jpg"' in rendered

    def test_handles_minimal_html_without_head_tag(self):
        minimal_html = '<!doctype html><html lang="ar" dir="rtl"><body><div id="root"></div></body></html>'
        rendered = post_preview.build_post_preview_html(
            minimal_html,
            {"id": 5, "title": "إعلان سريع", "summary": "نص مختصر"},
            site_origin="https://mahjar.example.org",
        )
        assert "<head>" in rendered
        assert "</head>" in rendered
        assert 'property="og:url" content="https://mahjar.example.org/posts/5"' in rendered
        assert '<div id="root"></div>' in rendered
