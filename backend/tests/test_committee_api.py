import time
import pytest
import app as backend_app


REQUIRED_MEMBER_KEYS = {
    "id",
    "fullName",
    "full_name",
    "role",
    "responsibilitySummary",
    "responsibility_summary",
    "avatarUrl",
    "avatar_url",
    "email",
    "phone",
    "displayOrder",
    "display_order",
}


@pytest.mark.api
class TestCommitteeDirectoryPayload:
    """Contract and data-integrity tests for GET /api/committee."""

    def test_returns_200_and_all_default_committee_members(self, client):
        response = client.get("/api/committee")

        assert response.status_code == 200
        assert response.content_type == "application/json"

        payload = response.get_json()
        assert isinstance(payload, list)
        assert len(payload) == 12

        chair = payload[0]
        assert REQUIRED_MEMBER_KEYS.issubset(chair.keys())
        assert chair["id"] == 1
        assert chair["fullName"] == "فادي وليد اغبارية"
        assert chair["full_name"] == "فادي وليد اغبارية"
        assert chair["role"] == "رئيس لجنة أولياء أمور الطلاب"
        assert chair["email"] == "Egb.fadi@gmail.com"
        assert "قيادة اللجنة وتمثيل الأهالي" in chair["responsibilitySummary"]
        assert chair["responsibilitySummary"] == chair["responsibility_summary"]

    @pytest.mark.parametrize(
        "input_record, expected_name, expected_role, expected_summary, expected_email",
        [
            (
                {
                    "id": 77,
                    "full_name": "ليلى عبد الرحمن",
                    "title": "عضو لجنة",
                    "responsibility_summary": "متابعة الأنشطة الثقافية.",
                    "contact_url": "laila@mahjar-parents.org",
                    "avatar_url": "  https://example.com/laila.webp  ",
                },
                "ليلى عبد الرحمن",
                "عضو لجنة",
                "متابعة الأنشطة الثقافية.",
                "laila@mahjar-parents.org",
            ),
            (
                {
                    "id": 88,
                    "fullName": "  سعيد محمود  ",
                    "role": "  أمين الصندوق  ",
                    "responsibilitySummary": "  إدارة الحسابات  ",
                    "contactUrl": "  saeed@mahjar-parents.org  ",
                    "avatarUrl": "   ",
                },
                "سعيد محمود",
                "أمين الصندوق",
                "إدارة الحسابات",
                "saeed@mahjar-parents.org",
            ),
        ],
        ids=["snake_case_input", "camelCase_with_whitespace"],
    )
    def test_normalizes_both_camel_and_snake_case_fields(
        self,
        client,
        mock_committee_source,
        input_record,
        expected_name,
        expected_role,
        expected_summary,
        expected_email,
    ):
        mock_committee_source([input_record])

        response = client.get("/api/committee")
        assert response.status_code == 200

        [member] = response.get_json()
        assert member["fullName"] == expected_name
        assert member["full_name"] == expected_name
        assert member["role"] == expected_role
        assert member["responsibilitySummary"] == expected_summary
        assert member["responsibility_summary"] == expected_summary
        assert member["email"] == expected_email
        assert member["avatarUrl"] == member["avatar_url"]

    def test_handles_empty_member_list_gracefully(self, client, mock_committee_source):
        mock_committee_source([])

        response = client.get("/api/committee")

        assert response.status_code == 200
        assert response.get_json() == []


@pytest.mark.api
class TestCommitteeOrdering:
    """Ordering and hierarchy tests for GET /api/committee."""

    def test_orders_records_by_explicit_display_order(
        self, client, member_factory, mock_committee_source
    ):
        unordered_records = [
            member_factory(id=4, fullName="ايمن طه غازي", role="عضو لجنة", displayOrder=4),
            member_factory(id=2, fullName="محمد شاكر إغبارية", role="نائب الرئيس", displayOrder=2),
            member_factory(id=1, fullName="فادي وليد اغبارية", role="رئيس لجنة أولياء أمور الطلاب", displayOrder=1),
            member_factory(id=3, fullName="طه علي اغباريه", role="أمين الصندوق", displayOrder=3),
        ]
        mock_committee_source(unordered_records)

        response = client.get("/api/committee")
        assert response.status_code == 200

        data = response.get_json()
        assert [item["id"] for item in data] == [1, 2, 3, 4]
        assert [item["displayOrder"] for item in data] == [1, 2, 3, 4]

    def test_orders_by_arabic_role_hierarchy_when_display_order_is_omitted(
        self, client, member_factory, mock_committee_source
    ):
        records_without_order = [
            member_factory(id=10, fullName="عضو عادي", role="عضو لجنة ومنسّق فعاليات ومبادرات"),
            member_factory(id=5, fullName="أمين الصندوق", role="أمين الصندوق ومسؤول التواصل مع الأهالي"),
            member_factory(id=8, fullName="رئيس اللجنة", role="رئيس لجنة أولياء أمور الطلاب"),
            member_factory(id=6, fullName="نائب الرئيس", role="نائب الرئيس"),
        ]
        mock_committee_source(records_without_order)

        response = client.get("/api/committee")
        assert response.status_code == 200

        data = response.get_json()
        assert [item["fullName"] for item in data] == [
            "رئيس اللجنة",
            "نائب الرئيس",
            "أمين الصندوق",
            "عضو عادي",
        ]
        assert [item["displayOrder"] for item in data] == [1, 2, 3, 4]


@pytest.mark.api
@pytest.mark.performance
class TestCommitteeCachingAndPerformance:
    """Caching, ETag conditional requests, and NFR performance tests for GET /api/committee."""

    def test_caches_responses_in_memory_across_repeated_reads(
        self, client, member_factory, mock_committee_source
    ):
        stats = mock_committee_source([
            member_factory(id=1, fullName="فادي وليد اغبارية", displayOrder=1)
        ])

        resp1 = client.get("/api/committee")
        resp2 = client.get("/api/committee")
        resp3 = client.get("/api/committee")

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp3.status_code == 200
        assert stats["calls"] == 1
        assert resp1.get_json() == resp2.get_json()

    def test_sets_cache_control_and_etag_headers_and_returns_304_on_match(self, client):
        resp1 = client.get("/api/committee")
        assert resp1.status_code == 200

        cache_control = resp1.headers.get("Cache-Control", "")
        assert "public" in cache_control
        assert f"max-age={backend_app.COMMITTEE_CACHE_TTL_SECONDS}" in cache_control

        etag = resp1.headers.get("ETag")
        assert etag is not None and etag.startswith('"') and etag.endswith('"')

        resp_304 = client.get("/api/committee", headers={"If-None-Match": etag})
        assert resp_304.status_code == 304
        assert resp_304.get_data() == b""

    def test_cache_invalidation_forces_fresh_reload(
        self, client, member_factory, mock_committee_source
    ):
        stats = mock_committee_source([
            member_factory(id=1, fullName="فادي وليد اغبارية", displayOrder=1)
        ])

        client.get("/api/committee")
        assert stats["calls"] == 1

        backend_app.clear_committee_cache()

        client.get("/api/committee")
        assert stats["calls"] == 2

    def test_response_time_stays_well_under_500ms_nfr_budget(self, client):
        start = time.perf_counter()
        response = client.get("/api/committee")
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert response.status_code == 200
        assert elapsed_ms < 500.0
