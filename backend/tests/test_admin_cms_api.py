import time
import pytest

import app as backend_app


@pytest.mark.api
class TestAdminAuthLifecycle:
    """Authentication, session/token handling, revocation, and cache security tests."""

    def test_login_returns_token_and_httponly_cookie_with_no_store_headers(
        self, client, admin_credentials
    ):
        resp = client.post("/api/admin/auth/login", json=admin_credentials)
        assert resp.status_code == 200
        assert "no-store" in resp.headers.get("Cache-Control", "")

        body = resp.get_json()
        assert body["authenticated"] is True
        assert body["username"] == "admin"
        assert body["tokenType"] == "Bearer"
        assert isinstance(body["token"], str) and len(body["token"]) > 20
        assert body["expiresIn"] == 3600

        set_cookie = resp.headers.get("Set-Cookie", "")
        assert "HttpOnly" in set_cookie
        assert "SameSite=Lax" in set_cookie

    def test_login_rejects_invalid_missing_and_unconfigured_credentials(
        self, client, tmp_path
    ):
        bad_pw = client.post(
            "/api/admin/auth/login",
            json={"username": "admin", "password": "wrong-password"},
        )
        assert bad_pw.status_code == 401
        assert bad_pw.get_json()["code"] == "INVALID_CREDENTIALS"

        missing = client.post("/api/admin/auth/login", json={"username": "admin"})
        assert missing.status_code == 400
        assert missing.get_json()["code"] == "MISSING_CREDENTIALS"

        unconfigured_app = backend_app.create_app({
            "TESTING": True,
            "ADMIN_PASSWORD": "",
            "ADMIN_PASSWORD_HASH": "",
            "CMS_DATA_FILE": str(tmp_path / "unconf.json"),
        })
        with unconfigured_app.test_client() as unconf_client:
            resp = unconf_client.post(
                "/api/admin/auth/login",
                json={"username": "admin", "password": "anything"},
            )
        assert resp.status_code == 503
        assert resp.get_json()["code"] == "ADMIN_AUTH_NOT_CONFIGURED"

    def test_me_works_with_bearer_token_and_session_cookie(
        self, client, admin_auth_headers, admin_session_client
    ):
        bearer_me = client.get("/api/admin/auth/me", headers=admin_auth_headers)
        assert bearer_me.status_code == 200
        assert bearer_me.get_json() == {
            "authenticated": True,
            "username": "admin",
            "authMethod": "bearer",
        }

        session_me = admin_session_client.get("/api/admin/auth/me")
        assert session_me.status_code == 200
        assert session_me.get_json() == {
            "authenticated": True,
            "username": "admin",
            "authMethod": "session",
        }

    def test_invalid_authorization_header_does_not_fall_back_to_session_cookie(
        self, admin_session_client
    ):
        resp = admin_session_client.get(
            "/api/admin/auth/me",
            headers={"Authorization": "Bearer invalid.tampered.token"},
        )
        assert resp.status_code == 401
        assert resp.get_json()["code"] == "INVALID_TOKEN"

    def test_logout_revokes_bearer_token_and_session_cookie(
        self, client, flask_app, admin_credentials, admin_auth_headers
    ):
        # Revoke Bearer token
        logout_bearer = client.post("/api/admin/auth/logout", headers=admin_auth_headers)
        assert logout_bearer.status_code == 200

        reused_bearer = client.get("/api/admin/auth/me", headers=admin_auth_headers)
        assert reused_bearer.status_code == 401
        assert reused_bearer.get_json()["code"] == "TOKEN_REVOKED"

        # Revoke session cookie and verify replaying old Set-Cookie value is rejected
        with flask_app.test_client() as sess_client:
            login_resp = sess_client.post("/api/admin/auth/login", json=admin_credentials)
            assert login_resp.status_code == 200
            raw_cookie = login_resp.headers.get("Set-Cookie", "").split(";", 1)[0]

            logout_sess = sess_client.post("/api/admin/auth/logout")
            assert logout_sess.status_code == 200

            after_logout = sess_client.get("/api/admin/auth/me")
            assert after_logout.status_code == 401

        # Replay captured cookie string in a fresh client with use_cookies=False
        replay_client = flask_app.test_client(use_cookies=False)
        replayed = replay_client.get(
            "/api/admin/auth/me",
            headers={"Cookie": raw_cookie},
        )
        assert replayed.status_code == 401
        assert replayed.get_json()["code"] == "TOKEN_REVOKED"

    def test_rejects_expired_bearer_token(self, tmp_path, admin_credentials):
        short_ttl_app = backend_app.create_app({
            "TESTING": True,
            "SECRET_KEY": "short-ttl-secret",
            "ADMIN_USERNAME": admin_credentials["username"],
            "ADMIN_PASSWORD": admin_credentials["password"],
            "ADMIN_TOKEN_TTL_SECONDS": 1,
            "CMS_DATA_FILE": str(tmp_path / "ttl.json"),
        })
        with short_ttl_app.test_client() as c:
            login_resp = c.post("/api/admin/auth/login", json=admin_credentials)
            token = login_resp.get_json()["token"]
            time.sleep(2.1)
            me_resp = c.get(
                "/api/admin/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert me_resp.status_code == 401
        assert me_resp.get_json()["code"] == "TOKEN_EXPIRED"

    @pytest.mark.parametrize(
        "method, path",
        [
            ("GET", "/api/admin/auth/me"),
            ("POST", "/api/admin/auth/logout"),
            ("GET", "/api/admin/committee"),
            ("POST", "/api/admin/committee"),
            ("PUT", "/api/admin/committee/1"),
            ("DELETE", "/api/admin/committee/1"),
            ("GET", "/api/admin/posts"),
            ("POST", "/api/admin/posts"),
            ("PUT", "/api/admin/posts/1"),
            ("DELETE", "/api/admin/posts/1"),
            ("GET", "/api/admin/media-links"),
            ("POST", "/api/admin/media-links"),
            ("PUT", "/api/admin/media-links/1"),
            ("DELETE", "/api/admin/media-links/1"),
            ("POST", "/api/admin/posts/1/media-links"),
            ("PUT", "/api/admin/posts/1/media-links/1"),
            ("DELETE", "/api/admin/posts/1/media-links/1"),
            ("GET", "/api/admin/forms"),
            ("POST", "/api/admin/forms"),
            ("PUT", "/api/admin/forms/1"),
            ("DELETE", "/api/admin/forms/1"),
        ],
    )
    def test_all_admin_endpoints_reject_unauthenticated_requests(
        self, client, method, path
    ):
        resp = client.open(path, method=method, json={})
        assert resp.status_code == 401
        assert resp.headers.get("WWW-Authenticate") == "Bearer"
        assert "no-store" in resp.headers.get("Cache-Control", "")


@pytest.mark.api
class TestAdminCommitteeCRUD:
    """Authenticated CRUD, XSS sanitization, and cache invalidation for committee members."""

    def test_create_update_delete_committee_member_and_sync_public_cache(
        self, client, admin_auth_headers
    ):
        initial_public = client.get("/api/committee")
        assert initial_public.status_code == 200
        initial_etag = initial_public.headers.get("ETag")
        initial_count = len(initial_public.get_json())

        # Create with XSS markup that must be sanitized
        create_resp = client.post(
            "/api/admin/committee",
            headers=admin_auth_headers,
            json={
                "fullName": "سمير <b>محمود</b> <script>alert(1)</script> عودة",
                "role": "عضو <img src=x onerror=alert(1)> لجنة",
                "responsibilitySummary": "متابعة <svg onload=alert(1)></svg> شؤون البيئة المدرسية.",
                "email": "samir@mahjar.org",
                "phone": "052-1112233",
                "avatarUrl": "/api/media/images/0123456789abcdef.webp",
                "displayOrder": 20,
            },
        )
        assert create_resp.status_code == 201
        created = create_resp.get_json()
        member_id = created["id"]
        assert created["fullName"] == "سمير محمود عودة"
        assert created["role"] == "عضو لجنة"
        assert created["responsibilitySummary"] == "متابعة شؤون البيئة المدرسية."
        assert "<" not in created["fullName"]
        assert "<" not in created["responsibilitySummary"]

        # Public endpoint reflects creation immediately with updated ETag
        after_create_public = client.get("/api/committee")
        assert len(after_create_public.get_json()) == initial_count + 1
        assert after_create_public.headers.get("ETag") != initial_etag
        assert any(m["id"] == member_id for m in after_create_public.get_json())

        # Update member
        update_resp = client.put(
            f"/api/admin/committee/{member_id}",
            headers=admin_auth_headers,
            json={
                "role": "منسق <iframe></iframe> السلامة",
                "avatarUrl": "https://cdn.example.com/avatars/samir.webp",
            },
        )
        assert update_resp.status_code == 200
        updated = update_resp.get_json()
        assert updated["role"] == "منسق السلامة"
        assert updated["avatarUrl"] == "https://cdn.example.com/avatars/samir.webp"
        assert updated["fullName"] == "سمير محمود عودة"

        # Delete member
        delete_resp = client.delete(
            f"/api/admin/committee/{member_id}",
            headers=admin_auth_headers,
        )
        assert delete_resp.status_code == 200
        assert delete_resp.get_json()["deleted"] is True

        after_delete_public = client.get("/api/committee")
        assert len(after_delete_public.get_json()) == initial_count
        assert not any(m["id"] == member_id for m in after_delete_public.get_json())

    def test_committee_crud_works_via_session_cookie(self, admin_session_client):
        list_resp = admin_session_client.get("/api/admin/committee")
        assert list_resp.status_code == 200
        assert len(list_resp.get_json()) == 12

        create_resp = admin_session_client.post(
            "/api/admin/committee",
            json={
                "fullName": "نورا خالد",
                "role": "عضو لجنة",
                "responsibilitySummary": "دعم الأنشطة الثقافية.",
            },
        )
        assert create_resp.status_code == 201

    def test_committee_rejects_invalid_inputs_and_missing_ids(
        self, client, admin_auth_headers
    ):
        xss_only = client.post(
            "/api/admin/committee",
            headers=admin_auth_headers,
            json={"fullName": "<script>alert(1)</script>", "role": "عضو"},
        )
        assert xss_only.status_code == 400

        bad_avatar_js = client.post(
            "/api/admin/committee",
            headers=admin_auth_headers,
            json={
                "fullName": "عضو صالح",
                "role": "عضو",
                "avatarUrl": "javascript:alert(1)",
            },
        )
        assert bad_avatar_js.status_code == 400

        bad_avatar_svg = client.post(
            "/api/admin/committee",
            headers=admin_auth_headers,
            json={
                "fullName": "عضو صالح",
                "role": "عضو",
                "avatarUrl": "https://example.com/avatar.svg",
            },
        )
        assert bad_avatar_svg.status_code == 400

        bad_email = client.post(
            "/api/admin/committee",
            headers=admin_auth_headers,
            json={"fullName": "عضو صالح", "role": "عضو", "email": "not-an-email"},
        )
        assert bad_email.status_code == 400

        bool_order = client.post(
            "/api/admin/committee",
            headers=admin_auth_headers,
            json={"fullName": "عضو صالح", "role": "عضو", "displayOrder": True},
        )
        assert bool_order.status_code == 400

        assert (
            client.put("/api/admin/committee/9999", headers=admin_auth_headers, json={"role": "عضو"}).status_code
            == 404
        )
        assert (
            client.delete("/api/admin/committee/9999", headers=admin_auth_headers).status_code
            == 404
        )


@pytest.mark.api
class TestAdminPostsCRUD:
    """Authenticated CRUD, sanitization, media link validation, and cache sync for posts."""

    def test_create_update_delete_post_and_sync_public_feed(
        self, client, admin_auth_headers
    ):
        initial_feed = client.get("/api/posts")
        initial_etag = initial_feed.headers.get("ETag")
        initial_count = len(initial_feed.get_json())

        create_resp = client.post(
            "/api/admin/posts",
            headers=admin_auth_headers,
            json={
                "title": "اجتماع <script>alert(1)</script> أولياء الأمور",
                "summary": "دعوة عامة <b>لجميع الأهالي</b> للحضور والمشاركة.",
                "category": "upcoming_event",
                "publishedAt": "2026-11-26T09:00:00Z",
                "eventDate": "2026-12-10",
                "imageUrl": "https://cdn.example.com/flyer.webp",
                "mediaLinks": [
                    {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "title": "فيديو <b>تعريفي</b>"}
                ],
            },
        )
        assert create_resp.status_code == 201
        created = create_resp.get_json()
        post_id = created["id"]
        assert created["title"] == "اجتماع أولياء الأمور"
        assert created["summary"] == "دعوة عامة لجميع الأهالي للحضور والمشاركة."
        assert len(created["mediaLinks"]) == 1
        assert created["mediaLinks"][0]["embedUrl"] == "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"
        assert created["mediaLinks"][0]["title"] == "فيديو تعريفي"

        public_after_create = client.get("/api/posts")
        assert len(public_after_create.get_json()) == initial_count + 1
        assert public_after_create.headers.get("ETag") != initial_etag
        assert public_after_create.get_json()[0]["id"] == post_id

        # Update post
        update_resp = client.put(
            f"/api/admin/posts/{post_id}",
            headers=admin_auth_headers,
            json={
                "title": "اجتماع أولياء الأمور المعدّل",
                "category": "updates",
            },
        )
        assert update_resp.status_code == 200
        updated = update_resp.get_json()
        assert updated["title"] == "اجتماع أولياء الأمور المعدّل"
        assert updated["category"] == "updates"
        assert len(updated["mediaLinks"]) == 1

        # Delete post
        del_resp = client.delete(f"/api/admin/posts/{post_id}", headers=admin_auth_headers)
        assert del_resp.status_code == 200
        assert del_resp.get_json()["deleted"] is True

        public_after_delete = client.get("/api/posts")
        assert len(public_after_delete.get_json()) == initial_count

    def test_post_rejects_invalid_category_dates_urls_and_missing_id(
        self, client, admin_auth_headers
    ):
        bad_cat = client.post(
            "/api/admin/posts",
            headers=admin_auth_headers,
            json={"title": "عنوان", "summary": "ملخص", "category": "invalid_cat"},
        )
        assert bad_cat.status_code == 400

        bad_date = client.post(
            "/api/admin/posts",
            headers=admin_auth_headers,
            json={"title": "عنوان", "summary": "ملخص", "eventDate": "10-12-2026"},
        )
        assert bad_date.status_code == 400

        bad_img = client.post(
            "/api/admin/posts",
            headers=admin_auth_headers,
            json={"title": "عنوان", "summary": "ملخص", "imageUrl": "http://insecure.com/a.jpg"},
        )
        assert bad_img.status_code == 400

        untrusted_media = client.post(
            "/api/admin/posts",
            headers=admin_auth_headers,
            json={
                "title": "عنوان",
                "summary": "ملخص",
                "mediaLinks": ["https://evil.example.com/video.mp4"],
            },
        )
        assert untrusted_media.status_code == 400
        assert untrusted_media.get_json()["code"] == "UNTRUSTED_MEDIA_DOMAIN"

        xss_title = client.post(
            "/api/admin/posts",
            headers=admin_auth_headers,
            json={"title": "<script>evil()</script>", "summary": "ملخص"},
        )
        assert xss_title.status_code == 400

        assert (
            client.put("/api/admin/posts/9999", headers=admin_auth_headers, json={"title": "تعديل"}).status_code
            == 404
        )
        assert client.delete("/api/admin/posts/9999", headers=admin_auth_headers).status_code == 404


@pytest.mark.api
class TestAdminMediaLinksCRUD:
    """Authenticated CRUD for standalone and post-scoped media links."""

    def test_standalone_and_post_scoped_media_links_crud_syncs_posts_feed(
        self, client, admin_auth_headers
    ):
        # Create post-scoped media link on post 1
        create_scoped = client.post(
            "/api/admin/posts/1/media-links",
            headers=admin_auth_headers,
            json={
                "url": "https://youtu.be/dQw4w9WgXcQ",
                "title": "كلمة <script>alert(1)</script> ترحيبية",
            },
        )
        assert create_scoped.status_code == 201
        link = create_scoped.get_json()
        link_id = link["id"]
        assert link["postId"] == 1
        assert link["provider"] == "youtube"
        assert link["embedUrl"] == "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"
        assert link["title"] == "كلمة ترحيبية"

        # Verify public GET /api/posts includes the new media link on post 1
        posts = client.get("/api/posts").get_json()
        post1 = next(p for p in posts if p["id"] == 1)
        assert any(m["embedUrl"] == link["embedUrl"] for m in post1["mediaLinks"])

        # Update via post-scoped endpoint
        upd_scoped = client.put(
            f"/api/admin/posts/1/media-links/{link_id}",
            headers=admin_auth_headers,
            json={
                "url": "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQr/view",
                "mediaType": "audio",
                "title": "تسجيل صوتي",
            },
        )
        assert upd_scoped.status_code == 200
        assert upd_scoped.get_json()["provider"] == "google_drive"
        assert upd_scoped.get_json()["mediaType"] == "audio"

        # Standalone list filtered by post_id
        list_resp = client.get("/api/admin/media-links?post_id=1", headers=admin_auth_headers)
        assert list_resp.status_code == 200
        assert len(list_resp.get_json()) == 1

        # Create standalone media link
        standalone_create = client.post(
            "/api/admin/media-links",
            headers=admin_auth_headers,
            json={
                "url": "https://vimeo.com/123456789",
                "title": "عرض مصور",
            },
        )
        assert standalone_create.status_code == 201
        standalone_id = standalone_create.get_json()["id"]
        assert standalone_create.get_json()["postId"] is None

        # Update standalone media link and attach to post 2
        standalone_update = client.put(
            f"/api/admin/media-links/{standalone_id}",
            headers=admin_auth_headers,
            json={"postId": 2, "title": "تقرير مصور"},
        )
        assert standalone_update.status_code == 200
        assert standalone_update.get_json()["postId"] == 2

        # Wrong post ownership returns 404 on post-scoped route
        wrong_owner = client.delete(
            f"/api/admin/posts/1/media-links/{standalone_id}",
            headers=admin_auth_headers,
        )
        assert wrong_owner.status_code == 404

        # Delete both links
        assert (
            client.delete(
                f"/api/admin/posts/1/media-links/{link_id}",
                headers=admin_auth_headers,
            ).status_code
            == 200
        )
        assert (
            client.delete(
                f"/api/admin/media-links/{standalone_id}",
                headers=admin_auth_headers,
            ).status_code
            == 200
        )

    @pytest.mark.parametrize(
        "bad_url, expected_code",
        [
            ("https://evil.com/video.mp4", "UNTRUSTED_MEDIA_DOMAIN"),
            ("https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ", "UNTRUSTED_MEDIA_DOMAIN"),
            ("http://www.youtube.com/watch?v=dQw4w9WgXcQ", "INSECURE_MEDIA_URL"),
            ("javascript:alert(1)", "INSECURE_MEDIA_URL"),
            ("https://user:pass@youtube.com/watch?v=dQw4w9WgXcQ", "UNSAFE_MEDIA_URL"),
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&x=<script>", "UNSAFE_MEDIA_URL"),
        ],
    )
    def test_rejects_untrusted_insecure_and_xss_media_urls(
        self, client, admin_auth_headers, bad_url, expected_code
    ):
        resp = client.post(
            "/api/admin/media-links",
            headers=admin_auth_headers,
            json={"url": bad_url},
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == expected_code

    def test_rejects_unknown_post_or_link_ids(self, client, admin_auth_headers):
        assert (
            client.post(
                "/api/admin/posts/9999/media-links",
                headers=admin_auth_headers,
                json={"url": "https://youtu.be/dQw4w9WgXcQ"},
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/admin/media-links",
                headers=admin_auth_headers,
                json={"postId": 9999, "url": "https://youtu.be/dQw4w9WgXcQ"},
            ).status_code
            == 404
        )
        assert (
            client.put(
                "/api/admin/media-links/9999",
                headers=admin_auth_headers,
                json={"title": "تعديل"},
            ).status_code
            == 404
        )
        assert (
            client.delete("/api/admin/media-links/9999", headers=admin_auth_headers).status_code
            == 404
        )


@pytest.mark.api
class TestAdminGoogleFormsCRUD:
    """Authenticated CRUD, trusted domain validation, and XSS sanitization for Google Forms."""

    def test_list_create_update_delete_google_forms(self, client, admin_auth_headers):
        initial_resp = client.get("/api/admin/forms", headers=admin_auth_headers)
        assert initial_resp.status_code == 200
        initial_forms = initial_resp.get_json()
        assert len(initial_forms) == 3

        create_resp = client.post(
            "/api/admin/forms",
            headers=admin_auth_headers,
            json={
                "formType": "event_registration",
                "title": "التسجيل في <script>alert(1)</script> يوم التراث",
                "description": "نرجو تعبئة <img src=x onerror=alert(1)> الاستمارة قبل الموعد.",
                "embedUrl": "https://docs.google.com/forms/d/e/1FAIpQLSeNewEventFormId123456/viewform?usp=sf_link&entry.1001=التراث",
                "active": True,
                "displayOrder": 4,
            },
        )
        assert create_resp.status_code == 201
        created = create_resp.get_json()
        form_id = created["id"]
        assert created["formType"] == "event_registration"
        assert created["title"] == "التسجيل في يوم التراث"
        assert created["description"] == "نرجو تعبئة الاستمارة قبل الموعد."
        assert created["provider"] == "google_forms"
        assert "embedded=true" in created["embedUrl"]
        assert "usp=" not in created["embedUrl"]
        assert "entry.1001=" in created["embedUrl"]
        assert created["canonicalUrl"].startswith("https://docs.google.com/forms/d/e/1FAIpQLSeNewEventFormId123456/viewform")

        update_resp = client.put(
            f"/api/admin/forms/{form_id}",
            headers=admin_auth_headers,
            json={
                "title": "التسجيل المحدّث في يوم التراث",
                "active": False,
            },
        )
        assert update_resp.status_code == 200
        updated = update_resp.get_json()
        assert updated["title"] == "التسجيل المحدّث في يوم التراث"
        assert updated["active"] is False

        del_resp = client.delete(f"/api/admin/forms/{form_id}", headers=admin_auth_headers)
        assert del_resp.status_code == 200
        assert del_resp.get_json()["deleted"] is True

        after_del = client.get("/api/admin/forms", headers=admin_auth_headers).get_json()
        assert len(after_del) == 3

    @pytest.mark.parametrize(
        "payload",
        [
            {
                "formType": "invalid_type",
                "title": "نموذج",
                "embedUrl": "https://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform",
            },
            {
                "formType": "feedback",
                "title": "نموذج",
                "embedUrl": "https://evil.com/phishing-form",
            },
            {
                "formType": "feedback",
                "title": "نموذج",
                "embedUrl": "https://docs.google.com.evil.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform",
            },
            {
                "formType": "feedback",
                "title": "نموذج",
                "embedUrl": "https://forms.gle.evil.com/fajYrbhcTA3xZa8d9",
            },
            {
                "formType": "feedback",
                "title": "نموذج",
                "embedUrl": "http://forms.gle/fajYrbhcTA3xZa8d9",
            },
            {
                "formType": "feedback",
                "title": "نموذج",
                "embedUrl": "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQr/edit",
            },
            {
                "formType": "feedback",
                "title": "نموذج",
                "embedUrl": "http://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform",
            },
            {
                "formType": "feedback",
                "title": "نموذج",
                "embedUrl": "javascript:alert(1)",
            },
            {
                "formType": "feedback",
                "title": "<script>alert(1)</script>",
                "embedUrl": "https://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform",
            },
            {
                "formType": "feedback",
                "title": "نموذج",
                "embedUrl": "https://docs.google.com/forms/d/e/1FAIpQLScAbCdEfGhIjKlMnOpQr/viewform",
                "active": "yes",
            },
        ],
    )
    def test_rejects_untrusted_domains_invalid_types_and_xss_in_forms(
        self, client, admin_auth_headers, payload
    ):
        resp = client.post("/api/admin/forms", headers=admin_auth_headers, json=payload)
        assert resp.status_code == 400

    def test_accepts_shortened_forms_gle_url_in_admin_forms(
        self, client, admin_auth_headers
    ):
        resp = client.post(
            "/api/admin/forms",
            headers=admin_auth_headers,
            json={
                "formType": "feedback",
                "title": "نموذج مختصر",
                "embedUrl": "https://forms.gle/fajYrbhcTA3xZa8d9",
                "active": True,
            },
        )
        assert resp.status_code == 201
        created = resp.get_json()
        assert created["provider"] == "google_forms"
        assert created["formId"] == "fajYrbhcTA3xZa8d9"
        assert created["canonicalUrl"] == "https://forms.gle/fajYrbhcTA3xZa8d9"
        assert created["embedUrl"] == "https://forms.gle/fajYrbhcTA3xZa8d9"

    def test_forms_returns_404_for_missing_id(self, client, admin_auth_headers):
        assert (
            client.put("/api/admin/forms/9999", headers=admin_auth_headers, json={"title": "تعديل"}).status_code
            == 404
        )
        assert client.delete("/api/admin/forms/9999", headers=admin_auth_headers).status_code == 404


@pytest.mark.api
class TestCMSPersistenceAcrossRestarts:
    """Verify atomic JSON store persists CMS mutations across app restarts."""

    def test_persists_committee_posts_media_links_and_forms_across_app_instances(
        self, tmp_path, admin_credentials
    ):
        data_file = str(tmp_path / "persisted_cms.json")
        config = {
            "TESTING": True,
            "SECRET_KEY": "persistence-test-secret",
            "ADMIN_USERNAME": admin_credentials["username"],
            "ADMIN_PASSWORD": admin_credentials["password"],
            "CMS_DATA_FILE": data_file,
        }

        app1 = backend_app.create_app(config)
        with app1.test_client() as c1:
            token = c1.post("/api/admin/auth/login", json=admin_credentials).get_json()["token"]
            headers = {"Authorization": f"Bearer {token}"}

            m_resp = c1.post(
                "/api/admin/committee",
                headers=headers,
                json={"fullName": "عضو مستمر", "role": "عضو لجنة"},
            )
            assert m_resp.status_code == 201
            member_id = m_resp.get_json()["id"]

            p_resp = c1.post(
                "/api/admin/posts",
                headers=headers,
                json={"title": "منشور مستمر", "summary": "ملخص مستمر", "category": "general"},
            )
            assert p_resp.status_code == 201
            post_id = p_resp.get_json()["id"]

            l_resp = c1.post(
                f"/api/admin/posts/{post_id}/media-links",
                headers=headers,
                json={"url": "https://youtu.be/dQw4w9WgXcQ", "title": "رابط مستمر"},
            )
            assert l_resp.status_code == 201

            f_resp = c1.post(
                "/api/admin/forms",
                headers=headers,
                json={
                    "formType": "feedback",
                    "title": "نموذج مستمر",
                    "embedUrl": "https://docs.google.com/forms/d/e/1FAIpQLSePersistedFormId12345/viewform",
                },
            )
            assert f_resp.status_code == 201
            form_id = f_resp.get_json()["id"]

        backend_app.clear_committee_cache()
        backend_app.clear_posts_cache()

        app2 = backend_app.create_app(config)
        with app2.test_client() as c2:
            token2 = c2.post("/api/admin/auth/login", json=admin_credentials).get_json()["token"]
            headers2 = {"Authorization": f"Bearer {token2}"}

            committee = c2.get("/api/committee").get_json()
            assert any(m["id"] == member_id and m["fullName"] == "عضو مستمر" for m in committee)

            posts = c2.get("/api/posts").get_json()
            persisted_post = next(p for p in posts if p["id"] == post_id)
            assert persisted_post["title"] == "منشور مستمر"
            assert len(persisted_post["mediaLinks"]) == 1
            assert persisted_post["mediaLinks"][0]["title"] == "رابط مستمر"

            forms = c2.get("/api/admin/forms", headers=headers2).get_json()
            assert any(f["id"] == form_id and f["title"] == "نموذج مستمر" for f in forms)
