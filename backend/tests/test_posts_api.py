import time
import pytest
import app as backend_app


REQUIRED_POST_KEYS = {
    "id",
    "title",
    "summary",
    "category",
    "publishedAt",
    "published_at",
    "eventDate",
    "event_date",
    "imageUrl",
    "image_url",
}

HEAVY_DETAIL_KEYS = {
    "body",
    "rawHtml",
    "raw_html",
    "fullContent",
    "full_content",
    "attachments",
}


@pytest.mark.api
class TestPostsFeedPayloadAndLightweightContract:
    """Contract, normalization, and lightweight payload tests for GET /api/posts."""

    def test_returns_200_and_all_default_posts_ordered_newest_first(self, client):
        response = client.get("/api/posts")

        assert response.status_code == 200
        assert response.content_type == "application/json"

        payload = response.get_json()
        assert isinstance(payload, list)
        assert len(payload) == 4

        first_post = payload[0]
        assert REQUIRED_POST_KEYS.issubset(first_post.keys())
        assert first_post["id"] == 1
        assert first_post["category"] == "upcoming_event"
        assert "يوم التراث" in first_post["title"]
        assert first_post["publishedAt"] == "2026-11-24T10:30:00Z"
        assert first_post["published_at"] == "2026-11-24T10:30:00Z"
        assert first_post["eventDate"] == "2026-12-05"
        assert first_post["event_date"] == "2026-12-05"

        # Verify default feed is ordered newest first
        published_timestamps = [item["publishedAt"] for item in payload]
        assert published_timestamps == sorted(published_timestamps, reverse=True)

    def test_normalizes_camel_and_snake_case_and_strips_heavy_fields_for_lightweight_payload(
        self, client, mock_posts_source
    ):
        long_text = "تفاصيل مطولة جداً عن الفعالية المدرسية " * 30
        mock_posts_source([
            {
                "id": 42,
                "title": "  فعالية القراءة الصباحية  ",
                "content": long_text,
                "category": "  student_activity  ",
                "published_at": "2026-11-20T09:00:00Z",
                "event_date": "2026-11-28",
                "image_url": "  https://example.com/reading.webp  ",
                "body": "LARGE_UNNECESSARY_BODY_BLOB " * 200,
                "raw_html": "<div>HEAVY HTML</div>" * 200,
                "attachments": ["file1.pdf", "file2.pdf"],
            }
        ])

        response = client.get("/api/posts")
        assert response.status_code == 200

        [post] = response.get_json()
        assert post["id"] == 42
        assert post["title"] == "فعالية القراءة الصباحية"
        assert post["category"] == "student_activity"
        assert post["publishedAt"] == "2026-11-20T09:00:00Z"
        assert post["published_at"] == "2026-11-20T09:00:00Z"
        assert post["eventDate"] == "2026-11-28"
        assert post["event_date"] == "2026-11-28"
        assert post["imageUrl"] == "https://example.com/reading.webp"
        assert post["image_url"] == "https://example.com/reading.webp"

        # Summary should be bounded/lightweight and heavy detail fields stripped
        assert len(post["summary"]) <= backend_app.POST_SUMMARY_MAX_LENGTH
        assert post["summary"].endswith("…") or post["summary"].endswith("...")
        assert HEAVY_DETAIL_KEYS.isdisjoint(post.keys())

    def test_handles_empty_posts_list_gracefully(self, client, mock_posts_source):
        mock_posts_source([])

        response = client.get("/api/posts")
        assert response.status_code == 200
        assert response.get_json() == []


@pytest.mark.api
class TestPostsOrderingAndCategoryFiltering:
    """Ordering (newest first) and category query parameter filtering tests for GET /api/posts."""

    def test_orders_posts_newest_first_with_id_tie_breaker(
        self, client, post_factory, mock_posts_source
    ):
        mock_posts_source([
            post_factory(id=10, title="إعلان قديم", publishedAt="2026-11-01T08:00:00Z"),
            post_factory(id=15, title="إعلان أحدث بنفس الوقت", publishedAt="2026-11-20T12:00:00Z"),
            post_factory(id=12, title="إعلان أقدم بنفس الوقت", publishedAt="2026-11-20T12:00:00Z"),
            post_factory(id=20, title="الإعلان الأحدث إطلاقاً", publishedAt="2026-11-25T09:30:00Z"),
        ])

        response = client.get("/api/posts")
        assert response.status_code == 200

        data = response.get_json()
        assert [item["id"] for item in data] == [20, 15, 12, 10]

    @pytest.mark.parametrize(
        "category, expected_count, expected_id",
        [
            ("upcoming_event", 1, 1),
            ("updates", 1, 2),
            ("student_activity", 1, 3),
            ("general", 1, 4),
            ("all", 4, 1),
            ("", 4, 1),
        ],
    )
    def test_filters_by_valid_category_query_parameter(
        self, client, category, expected_count, expected_id
    ):
        response = client.get(f"/api/posts?category={category}")
        assert response.status_code == 200

        data = response.get_json()
        assert len(data) == expected_count
        assert data[0]["id"] == expected_id
        if category and category != "all":
            assert all(item["category"] == category for item in data)

    def test_rejects_invalid_category_with_400_error(self, client):
        response = client.get("/api/posts?category=invalid_category_name")

        assert response.status_code == 400
        body = response.get_json()
        assert "error" in body
        assert "allowedCategories" in body


@pytest.mark.api
class TestPostsPagination:
    """Pagination support (limit, offset, page/per_page, envelope vs list) tests for GET /api/posts."""

    def test_supports_limit_and_offset_query_parameters(
        self, client, post_factory, mock_posts_source
    ):
        # 5 posts ordered newest first: IDs 5, 4, 3, 2, 1
        mock_posts_source([
            post_factory(id=i, publishedAt=f"2026-11-{10 + i:02d}T10:00:00Z")
            for i in range(1, 6)
        ])

        resp_page1 = client.get("/api/posts?limit=2&offset=0")
        assert resp_page1.status_code == 200
        assert [item["id"] for item in resp_page1.get_json()] == [5, 4]
        assert resp_page1.headers.get("X-Total-Count") == "5"
        assert resp_page1.headers.get("X-Has-More") == "true"

        resp_page2 = client.get("/api/posts?limit=2&offset=2")
        assert resp_page2.status_code == 200
        assert [item["id"] for item in resp_page2.get_json()] == [3, 2]
        assert resp_page2.headers.get("X-Has-More") == "true"

        resp_page3 = client.get("/api/posts?limit=2&offset=4")
        assert resp_page3.status_code == 200
        assert [item["id"] for item in resp_page3.get_json()] == [1]
        assert resp_page3.headers.get("X-Has-More") == "false"

    def test_supports_page_and_per_page_with_optional_metadata_envelope(
        self, client, post_factory, mock_posts_source
    ):
        mock_posts_source([
            post_factory(id=i, publishedAt=f"2026-11-{10 + i:02d}T10:00:00Z")
            for i in range(1, 6)
        ])

        response = client.get("/api/posts?page=2&per_page=2&envelope=true")
        assert response.status_code == 200

        body = response.get_json()
        assert isinstance(body, dict)
        assert [item["id"] for item in body["items"]] == [3, 2]
        assert body["pagination"] == {
            "total": 5,
            "limit": 2,
            "offset": 2,
            "page": 2,
            "perPage": 2,
            "totalPages": 3,
            "hasMore": True,
        }

    @pytest.mark.parametrize(
        "query_string",
        [
            "limit=0",
            "limit=-5",
            "limit=abc",
            "offset=-1",
            "offset=xyz",
            "page=0",
            "page=-2",
            "per_page=0",
        ],
    )
    def test_rejects_invalid_pagination_parameters_with_400(self, client, query_string):
        response = client.get(f"/api/posts?{query_string}")
        assert response.status_code == 400
        assert "error" in response.get_json()


@pytest.mark.api
@pytest.mark.performance
class TestPostsCachingAndPerformance:
    """In-memory caching, ETag 304 support, and <500ms TTFB performance tests for GET /api/posts."""

    def test_caches_normalized_posts_across_filtered_and_paginated_reads(
        self, client, post_factory, mock_posts_source
    ):
        stats = mock_posts_source([
            post_factory(id=1, category="general", publishedAt="2026-11-10T08:00:00Z"),
            post_factory(id=2, category="updates", publishedAt="2026-11-22T16:45:00Z"),
        ])

        resp1 = client.get("/api/posts")
        resp2 = client.get("/api/posts?category=updates")
        resp3 = client.get("/api/posts?limit=1")

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp3.status_code == 200
        assert stats["calls"] == 1

    def test_sets_cache_control_and_distinct_etag_per_query_and_returns_304(self, client):
        resp_all = client.get("/api/posts")
        resp_updates = client.get("/api/posts?category=updates")

        assert resp_all.status_code == 200
        assert resp_updates.status_code == 200

        etag_all = resp_all.headers.get("ETag")
        etag_updates = resp_updates.headers.get("ETag")
        assert etag_all is not None and etag_all.startswith('"')
        assert etag_updates is not None and etag_updates != etag_all

        cache_control = resp_all.headers.get("Cache-Control", "")
        assert "public" in cache_control
        assert f"max-age={backend_app.POSTS_CACHE_TTL_SECONDS}" in cache_control

        resp_304 = client.get("/api/posts", headers={"If-None-Match": etag_all})
        assert resp_304.status_code == 304
        assert resp_304.get_data() == b""

    def test_cache_invalidation_forces_fresh_posts_reload(
        self, client, post_factory, mock_posts_source
    ):
        stats = mock_posts_source([
            post_factory(id=1, category="general")
        ])

        client.get("/api/posts")
        assert stats["calls"] == 1

        backend_app.clear_posts_cache()

        client.get("/api/posts")
        assert stats["calls"] == 2

    def test_ttfb_and_response_time_stay_well_under_500ms_budget(
        self, client, post_factory, mock_posts_source
    ):
        # Populate 50 posts to simulate a realistic feed load
        mock_posts_source([
            post_factory(
                id=i,
                category="general" if i % 2 == 0 else "upcoming_event",
                publishedAt=f"2026-11-{(i % 28) + 1:02d}T10:00:00Z",
            )
            for i in range(1, 51)
        ])

        start = time.perf_counter()
        response = client.get("/api/posts?category=upcoming_event&limit=10&offset=0")
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert response.status_code == 200
        assert len(response.get_json()) == 10
        assert elapsed_ms < 500.0
