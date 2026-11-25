import time
import pytest
import app as backend_app


REQUIRED_FORM_KEYS = {
    "id",
    "formType",
    "form_type",
    "title",
    "description",
    "embedUrl",
    "embed_url",
    "canonicalUrl",
    "canonical_url",
    "directUrl",
    "direct_url",
    "provider",
    "formId",
    "form_id",
    "active",
    "displayOrder",
    "display_order",
}


@pytest.mark.api
class TestPublicFormsConfigPayload:
    """Contract and normalization tests for public GET /api/forms."""

    def test_returns_200_and_all_default_active_forms_without_auth(self, client):
        response = client.get("/api/forms")

        assert response.status_code == 200
        assert response.content_type == "application/json"
        assert response.headers.get("X-Total-Count") == "3"

        payload = response.get_json()
        assert isinstance(payload, list)
        assert [item["formType"] for item in payload] == [
            "feedback",
            "help_request",
            "event_registration",
        ]

        for item in payload:
            assert REQUIRED_FORM_KEYS.issubset(item.keys())
            assert item["active"] is True
            assert item["provider"] == "google_forms"
            assert item["embedUrl"].startswith("https://docs.google.com/forms/")
            assert "embedded=true" in item["embedUrl"]
            assert item["canonicalUrl"].startswith("https://docs.google.com/forms/")
            assert "embedded=true" not in item["canonicalUrl"]
            assert item["directUrl"] == item["canonicalUrl"]
            assert item["direct_url"] == item["canonicalUrl"]
            assert item["formId"] == item["form_id"]

    def test_supports_envelope_payload_with_by_type_and_trusted_domains(self, client):
        response = client.get("/api/forms?envelope=true")

        assert response.status_code == 200
        assert response.headers.get("X-Total-Count") == "3"

        body = response.get_json()
        assert isinstance(body, dict)
        assert body["total"] == 3
        assert body["allowedFormTypes"] == [
            "feedback",
            "help_request",
            "event_registration",
        ]
        assert body["trustedDomains"] == ["docs.google.com", "forms.gle"]
        assert len(body["items"]) == 3
        assert set(body["byType"].keys()) == {
            "feedback",
            "help_request",
            "event_registration",
        }
        assert len(body["byType"]["feedback"]) == 1
        assert len(body["byType"]["help_request"]) == 1
        assert len(body["byType"]["event_registration"]) == 1

    def test_normalizes_snake_case_fields_and_handles_empty_list(
        self, client, mock_forms_source
    ):
        mock_forms_source([
            {
                "id": 55,
                "form_type": "  help_request  ",
                "title": "  نموذج طلب مساعدة  ",
                "description": "  وصف مختصر  ",
                "embed_url": "https://docs.google.com/forms/d/e/1FAIpQLScSnakeCaseFormId12345/viewform?usp=sf_link",
                "active": True,
                "display_order": 2,
            }
        ])

        response = client.get("/api/forms")
        assert response.status_code == 200
        assert response.headers.get("X-Total-Count") == "1"

        [form] = response.get_json()
        assert form["id"] == 55
        assert form["formType"] == "help_request"
        assert form["form_type"] == "help_request"
        assert form["title"] == "نموذج طلب مساعدة"
        assert form["description"] == "وصف مختصر"
        assert form["displayOrder"] == 2
        assert form["display_order"] == 2
        assert (
            form["embedUrl"]
            == "https://docs.google.com/forms/d/e/1FAIpQLScSnakeCaseFormId12345/viewform?embedded=true"
        )
        assert (
            form["canonicalUrl"]
            == "https://docs.google.com/forms/d/e/1FAIpQLScSnakeCaseFormId12345/viewform"
        )

        backend_app.clear_forms_cache()
        mock_forms_source([])

        empty_resp = client.get("/api/forms")
        assert empty_resp.status_code == 200
        assert empty_resp.headers.get("X-Total-Count") == "0"
        assert empty_resp.get_json() == []

        empty_env = client.get("/api/forms?envelope=true")
        assert empty_env.status_code == 200
        env_body = empty_env.get_json()
        assert env_body["items"] == []
        assert env_body["total"] == 0
        assert env_body["byType"] == {
            "feedback": [],
            "help_request": [],
            "event_registration": [],
        }

    def test_exposes_active_shortened_forms_gle_urls(
        self, client, form_factory, mock_forms_source
    ):
        mock_forms_source([
            form_factory(
                id=77,
                formType="feedback",
                title="نموذج عبر رابط مختصر",
                embedUrl="https://forms.gle/fajYrbhcTA3xZa8d9",
                canonicalUrl="https://forms.gle/fajYrbhcTA3xZa8d9",
                formId="fajYrbhcTA3xZa8d9",
            )
        ])

        response = client.get("/api/forms")
        assert response.status_code == 200
        [form] = response.get_json()
        assert form["id"] == 77
        assert form["provider"] == "google_forms"
        assert form["formId"] == "fajYrbhcTA3xZa8d9"
        assert form["embedUrl"] == "https://forms.gle/fajYrbhcTA3xZa8d9"
        assert form["canonicalUrl"] == "https://forms.gle/fajYrbhcTA3xZa8d9"
        assert form["directUrl"] == "https://forms.gle/fajYrbhcTA3xZa8d9"


@pytest.mark.api
class TestPublicFormsFilteringAndOrdering:
    """Active-status filtering, type filtering, deterministic ordering, and error handling."""

    def test_excludes_inactive_and_non_boolean_active_records(
        self, client, form_factory, mock_forms_source
    ):
        mock_forms_source([
            form_factory(id=1, formType="feedback", title="نشط فعلياً", active=True),
            form_factory(id=2, formType="help_request", title="معطل", active=False),
            form_factory(id=3, formType="event_registration", title="قيمة فارغة", active=None),
            form_factory(id=4, formType="feedback", title="نص غير منطقي", active="true"),
            form_factory(id=5, formType="feedback", title="صفر", active=0),
        ])

        response = client.get("/api/forms")
        assert response.status_code == 200
        data = response.get_json()
        assert [item["id"] for item in data] == [1]

    @pytest.mark.parametrize(
        "query_param",
        ["type", "formType", "form_type"],
    )
    @pytest.mark.parametrize(
        "form_type",
        ["feedback", "help_request", "event_registration"],
    )
    def test_filters_by_query_parameter_variants(self, client, query_param, form_type):
        response = client.get(f"/api/forms?{query_param}={form_type}")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 1
        assert data[0]["formType"] == form_type
        assert response.headers.get("X-Total-Count") == "1"

    def test_supports_all_and_empty_type_query_and_path_route(self, client):
        resp_all = client.get("/api/forms?type=all")
        assert resp_all.status_code == 200
        assert len(resp_all.get_json()) == 3

        resp_empty = client.get("/api/forms?type=")
        assert resp_empty.status_code == 200
        assert len(resp_empty.get_json()) == 3

        for form_type in ("feedback", "help_request", "event_registration"):
            path_resp = client.get(f"/api/forms/{form_type}")
            assert path_resp.status_code == 200
            items = path_resp.get_json()
            assert len(items) == 1
            assert items[0]["formType"] == form_type

            env_resp = client.get(f"/api/forms/{form_type}?envelope=true")
            assert env_resp.status_code == 200
            env_body = env_resp.get_json()
            assert env_body["total"] == 1
            assert len(env_body["items"]) == 1
            assert env_body["items"][0]["formType"] == form_type

    def test_rejects_unknown_form_type_in_query_and_path_with_400(self, client):
        q_resp = client.get("/api/forms?type=unknown_type")
        assert q_resp.status_code == 400
        q_body = q_resp.get_json()
        assert q_body["code"] == "INVALID_FORM_TYPE"
        assert "allowedFormTypes" in q_body

        p_resp = client.get("/api/forms/unknown_type")
        assert p_resp.status_code == 400
        p_body = p_resp.get_json()
        assert p_body["code"] == "INVALID_FORM_TYPE"
        assert p_body["allowedFormTypes"] == [
            "feedback",
            "help_request",
            "event_registration",
        ]

    def test_orders_by_display_order_then_type_priority_then_id(
        self, client, form_factory, mock_forms_source
    ):
        mock_forms_source([
            form_factory(id=10, formType="event_registration", title="تسجيل بدون ترتيب", displayOrder=None),
            form_factory(id=11, formType="feedback", title="آراء بدون ترتيب 2", displayOrder=None),
            form_factory(id=5, formType="feedback", title="آراء بدون ترتيب 1", displayOrder=None),
            form_factory(id=20, formType="help_request", title="مساعدة بترتيب 2", displayOrder=2),
            form_factory(id=21, formType="event_registration", title="تسجيل بترتيب 1", displayOrder=1),
        ])

        response = client.get("/api/forms")
        assert response.status_code == 200
        ids = [item["id"] for item in response.get_json()]
        assert ids == [21, 20, 5, 11, 10]


@pytest.mark.api
class TestPublicFormsDomainValidationDefenseInDepth:
    """Defense-in-depth domain validation and sanitization for stored form configs."""

    @pytest.mark.parametrize(
        "bad_url",
        [
            "https://evil.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform",
            "https://docs.google.com.evil.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform",
            "https://forms.gle.evil.com/fajYrbhcTA3xZa8d9",
            "http://forms.gle/fajYrbhcTA3xZa8d9",
            "https://forms.gle/fajYrbhcTA3xZa8d9/extra",
            "http://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform",
            "javascript:alert(1)",
            "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQr/edit",
            "https://docs.google.com:8443/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform",
            "https://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/../../etc/passwd",
        ],
    )
    def test_silently_excludes_untrusted_or_malformed_stored_urls(
        self, client, form_factory, mock_forms_source, bad_url
    ):
        mock_forms_source([
            form_factory(id=1, formType="feedback", title="نموذج موثوق"),
            form_factory(id=2, formType="help_request", title="نموذج مخترق", embedUrl=bad_url, canonicalUrl=bad_url),
        ])

        response = client.get("/api/forms")
        assert response.status_code == 200
        data = response.get_json()
        assert [item["id"] for item in data] == [1]

    def test_excludes_invalid_form_type_and_xss_only_titles_and_sanitizes_output(
        self, client, form_factory, mock_forms_source
    ):
        mock_forms_source([
            form_factory(
                id=1,
                formType="feedback",
                title="نموذج <script>alert(1)</script> المقترحات",
                description="يرجى <img src=x onerror=alert(1)> التعبئة",
                embedUrl=(
                    "https://docs.google.com/forms/d/e/1FAIpQLScSafeFormId123456/viewform"
                    "?usp=sf_link&evil=1&entry.101=الصف+الأول&entry.202=%3Cscript%3Ealert(1)%3C/script%3E"
                ),
            ),
            form_factory(id=2, formType="unknown_kind", title="نوع غير صالح"),
            form_factory(id=3, formType="help_request", title="<script>alert(1)</script>"),
            form_factory(id=4, formType="event_registration", title="   "),
        ])

        response = client.get("/api/forms")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 1
        [form] = data
        assert form["id"] == 1
        assert form["title"] == "نموذج المقترحات"
        assert form["description"] == "يرجى التعبئة"
        assert "usp=" not in form["embedUrl"]
        assert "evil=" not in form["embedUrl"]
        assert "entry.101=" in form["embedUrl"]
        assert "entry.202=" not in form["embedUrl"]
        assert "<script" not in form["embedUrl"].lower()


@pytest.mark.api
class TestGoogleFormsValidateEndpoint:
    """Contract and security validation tests for POST /api/forms/validate."""

    @pytest.mark.parametrize("field_key", ["url", "embedUrl", "embed_url"])
    def test_accepts_valid_google_forms_urls_across_field_aliases(self, client, field_key):
        raw_url = (
            "https://docs.google.com/forms/u/0/d/e/"
            "1FAIpQLScValidEndpointFormId123/viewform?usp=sf_link&entry.555=ولي+أمر"
        )
        response = client.post("/api/forms/validate", json={field_key: raw_url})

        assert response.status_code == 200
        body = response.get_json()
        assert body["valid"] is True
        assert body["provider"] == "google_forms"
        assert body["trustedDomain"] == "docs.google.com"
        assert body["formId"] == "1FAIpQLScValidEndpointFormId123"
        assert body["form_id"] == "1FAIpQLScValidEndpointFormId123"
        assert body["embedUrl"].startswith(
            "https://docs.google.com/forms/d/e/1FAIpQLScValidEndpointFormId123/viewform?embedded=true"
        )
        assert "entry.555=" in body["embedUrl"]
        assert "usp=" not in body["embedUrl"]
        assert body["embed_url"] == body["embedUrl"]
        assert body["directUrl"] == body["canonicalUrl"]
        assert body["direct_url"] == body["canonicalUrl"]
        assert "embedded=true" not in body["canonicalUrl"]

    def test_accepts_non_e_google_forms_path(self, client):
        response = client.post(
            "/api/forms/validate",
            json={"url": "https://docs.google.com/forms/d/1AbCdEfGhIjKlMnOpQrStUvWxYz"},
        )
        assert response.status_code == 200
        body = response.get_json()
        assert body["canonicalUrl"] == "https://docs.google.com/forms/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/viewform"
        assert body["embedUrl"] == "https://docs.google.com/forms/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/viewform?embedded=true"

    def test_accepts_shortened_forms_gle_url(self, client):
        response = client.post(
            "/api/forms/validate",
            json={"url": "https://forms.gle/fajYrbhcTA3xZa8d9"},
        )
        assert response.status_code == 200
        body = response.get_json()
        assert body["valid"] is True
        assert body["provider"] == "google_forms"
        assert body["trustedDomain"] == "forms.gle"
        assert body["formId"] == "fajYrbhcTA3xZa8d9"
        assert body["form_id"] == "fajYrbhcTA3xZa8d9"
        assert body["canonicalUrl"] == "https://forms.gle/fajYrbhcTA3xZa8d9"
        assert body["directUrl"] == "https://forms.gle/fajYrbhcTA3xZa8d9"
        assert body["embedUrl"] == "https://forms.gle/fajYrbhcTA3xZa8d9"

    def test_rejects_invalid_json_body(self, client):
        response = client.post(
            "/api/forms/validate",
            data="not-json",
            content_type="application/json",
        )
        assert response.status_code == 400
        assert response.get_json()["code"] == "INVALID_JSON"

    @pytest.mark.parametrize(
        "payload, expected_code",
        [
            ({}, "INVALID_FORM_URL"),
            ({"url": ""}, "INVALID_FORM_URL"),
            ({"url": "https://evil.com/forms/d/e/1FAIpQLScAbCdEfGhIjKl/viewform"}, "UNTRUSTED_FORM_DOMAIN"),
            ({"url": "https://docs.google.com.evil.com/forms/d/e/1FAIpQLScAbCdEfGhIjKl/viewform"}, "UNTRUSTED_FORM_DOMAIN"),
            ({"url": "https://forms.gle.evil.com/fajYrbhcTA3xZa8d9"}, "UNTRUSTED_FORM_DOMAIN"),
            ({"url": "http://forms.gle/fajYrbhcTA3xZa8d9"}, "INSECURE_FORM_URL"),
            ({"url": "https://forms.gle/short"}, "INVALID_FORM_URL"),
            ({"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}, "UNTRUSTED_FORM_DOMAIN"),
            ({"url": "https://docs.google.com/document/d/1AbCdEfGhIjKl/edit"}, "INVALID_FORM_URL"),
            ({"url": "https://docs.google.com/forms/d/1AbCdEfGhIjKlMnOpQr/edit"}, "INVALID_FORM_URL"),
            ({"url": "http://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKl/viewform"}, "INSECURE_FORM_URL"),
            ({"url": "javascript:alert(1)"}, "INSECURE_FORM_URL"),
            ({"url": "https://user:pass@docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKl/viewform"}, "UNSAFE_FORM_URL"),
            ({"url": "https://docs.google.com:8443/forms/d/e/1FAIpQLScAbCdEfGhIjKl/viewform"}, "UNSAFE_FORM_URL"),
            ({"url": "https://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKl/../../etc/passwd"}, "UNSAFE_FORM_URL"),
            ({"url": "https://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKl/viewform?x=<script>"}, "UNSAFE_FORM_URL"),
        ],
    )
    def test_rejects_untrusted_insecure_and_malformed_urls(
        self, client, payload, expected_code
    ):
        response = client.post("/api/forms/validate", json=payload)
        assert response.status_code == 400
        assert response.get_json()["code"] == expected_code


@pytest.mark.api
@pytest.mark.performance
class TestPublicFormsAdminSyncAndCaching:
    """Cache invalidation on Admin mutations, HTTP caching/304, and <500ms latency tests."""

    def test_admin_create_update_delete_immediately_syncs_public_forms_endpoints(
        self, client, admin_auth_headers
    ):
        # Prime cache
        initial = client.get("/api/forms")
        assert initial.status_code == 200
        assert len(initial.get_json()) == 3

        # Admin creates an active form
        create_resp = client.post(
            "/api/admin/forms",
            headers=admin_auth_headers,
            json={
                "formType": "event_registration",
                "title": "التسجيل في يوم الرياضة",
                "embedUrl": "https://docs.google.com/forms/d/e/1FAIpQLSeSportsDayForm12345/viewform",
                "active": True,
                "displayOrder": 4,
            },
        )
        assert create_resp.status_code == 201
        created_id = create_resp.get_json()["id"]

        after_create = client.get("/api/forms").get_json()
        assert len(after_create) == 4
        assert any(item["id"] == created_id for item in after_create)

        # Admin disables the form -> hidden from public endpoint immediately
        disable_resp = client.put(
            f"/api/admin/forms/{created_id}",
            headers=admin_auth_headers,
            json={"active": False, "title": "نموذج معطل مؤقتاً"},
        )
        assert disable_resp.status_code == 200

        after_disable = client.get("/api/forms").get_json()
        assert len(after_disable) == 3
        assert all(item["id"] != created_id for item in after_disable)

        by_type = client.get("/api/forms/event_registration").get_json()
        assert all(item["id"] != created_id for item in by_type)

        # Admin re-enables and updates -> visible again
        enable_resp = client.put(
            f"/api/admin/forms/{created_id}",
            headers=admin_auth_headers,
            json={"active": True, "title": "التسجيل المحدّث ليوم الرياضة"},
        )
        assert enable_resp.status_code == 200

        after_enable = client.get("/api/forms/event_registration").get_json()
        assert any(
            item["id"] == created_id and item["title"] == "التسجيل المحدّث ليوم الرياضة"
            for item in after_enable
        )

        # Admin deletes -> removed from public endpoint
        del_resp = client.delete(
            f"/api/admin/forms/{created_id}", headers=admin_auth_headers
        )
        assert del_resp.status_code == 200
        assert len(client.get("/api/forms").get_json()) == 3

    def test_caches_active_forms_across_filtered_and_path_reads(
        self, client, form_factory, mock_forms_source
    ):
        stats = mock_forms_source([
            form_factory(id=1, formType="feedback", active=True),
            form_factory(id=2, formType="help_request", active=True),
        ])

        r1 = client.get("/api/forms")
        r2 = client.get("/api/forms?type=feedback")
        r3 = client.get("/api/forms/feedback")

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 200
        assert stats["calls"] == 1

    def test_sets_cache_control_and_distinct_etag_and_returns_304(self, client):
        resp_all = client.get("/api/forms")
        resp_feedback = client.get("/api/forms?type=feedback")

        assert resp_all.status_code == 200
        assert resp_feedback.status_code == 200

        etag_all = resp_all.headers.get("ETag")
        etag_feedback = resp_feedback.headers.get("ETag")
        assert etag_all is not None and etag_all.startswith('"')
        assert etag_feedback is not None and etag_feedback != etag_all

        cache_control = resp_all.headers.get("Cache-Control", "")
        assert "public" in cache_control
        assert f"max-age={backend_app.FORMS_CACHE_TTL_SECONDS}" in cache_control

        resp_304 = client.get("/api/forms", headers={"If-None-Match": etag_all})
        assert resp_304.status_code == 304
        assert resp_304.get_data() == b""

    def test_cache_invalidation_forces_fresh_reload(
        self, client, form_factory, mock_forms_source
    ):
        stats = mock_forms_source([form_factory(id=1, formType="feedback", active=True)])

        client.get("/api/forms")
        assert stats["calls"] == 1

        backend_app.clear_forms_cache()

        client.get("/api/forms")
        assert stats["calls"] == 2

    def test_response_time_stays_well_under_500ms_nfr_budget(self, client):
        start = time.perf_counter()
        response = client.get("/api/forms")
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert response.status_code == 200
        assert elapsed_ms < 500.0
