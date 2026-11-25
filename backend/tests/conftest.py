import copy
from typing import Callable, Dict, List
import pytest
from werkzeug.security import generate_password_hash
import app as backend_app


@pytest.fixture(autouse=True)
def reset_caches():
    """Automatically isolate tests by clearing in-memory caches before and after each test."""
    backend_app.clear_committee_cache()
    if hasattr(backend_app, "clear_posts_cache"):
        backend_app.clear_posts_cache()
    if hasattr(backend_app, "clear_forms_cache"):
        backend_app.clear_forms_cache()
    yield
    backend_app.clear_committee_cache()
    if hasattr(backend_app, "clear_posts_cache"):
        backend_app.clear_posts_cache()
    if hasattr(backend_app, "clear_forms_cache"):
        backend_app.clear_forms_cache()


@pytest.fixture
def admin_credentials() -> Dict[str, str]:
    """Provide default admin test credentials."""
    return {
        "username": "admin",
        "password": "MahjarAdmin!2026",
    }


@pytest.fixture
def flask_app(tmp_path, admin_credentials):
    """Create an isolated Flask application instance via the application factory."""
    return backend_app.create_app({
        "TESTING": True,
        "MEDIA_UPLOAD_DIR": str(tmp_path / "uploads"),
        "SECRET_KEY": "test-secret-key-for-mahjar-admin-cms",
        "ADMIN_USERNAME": admin_credentials["username"],
        "ADMIN_PASSWORD_HASH": generate_password_hash(admin_credentials["password"]),
        "ADMIN_TOKEN_TTL_SECONDS": 3600,
        "CMS_DATA_FILE": str(tmp_path / "cms_data.json"),
    })


@pytest.fixture
def client(flask_app):
    """Provide a Flask test client for sending simulated HTTP requests."""
    with flask_app.test_client() as test_client:
        yield test_client


@pytest.fixture
def admin_auth_headers(flask_app, admin_credentials) -> Dict[str, str]:
    """Obtain a Bearer token via a separate test client so `client` has no session cookie."""
    auth_client = flask_app.test_client()
    resp = auth_client.post("/api/admin/auth/login", json=admin_credentials)
    assert resp.status_code == 200, f"Login failed in fixture: {resp.get_json()}"
    token = resp.get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_session_client(flask_app, admin_credentials):
    """Provide a Flask test client authenticated via HttpOnly session cookie."""
    session_client = flask_app.test_client()
    resp = session_client.post("/api/admin/auth/login", json=admin_credentials)
    assert resp.status_code == 200, f"Session login failed in fixture: {resp.get_json()}"
    return session_client


@pytest.fixture
def member_factory() -> Callable[..., Dict]:
    """Factory fixture to build customized committee member records cleanly in tests."""
    counter = 100

    def _create_member(**overrides) -> Dict:
        nonlocal counter
        counter += 1
        base = {
            "id": counter,
            "fullName": f"عضو تجريبي {counter}",
            "role": "عضو لجنة ومنسّق فعاليات ومبادرات",
            "responsibilitySummary": "تخطيط وتنسيق الفعاليات اللامنهجية، وطرح المبادرات التربوية.",
            "email": f"member{counter}@mahjar-parents.org",
            "phone": "0500000000",
            "avatarUrl": "",
        }
        base.update(overrides)
        return base

    return _create_member


@pytest.fixture
def mock_committee_source(monkeypatch) -> Callable[[List[Dict]], Dict[str, int]]:
    """Helper fixture to stub `load_committee_members` and track invocation count."""
    def _configure(records: List[Dict]) -> Dict[str, int]:
        stats = {"calls": 0}

        def _fake_loader():
            stats["calls"] += 1
            return copy.deepcopy(records)

        monkeypatch.setattr(backend_app, "load_committee_members", _fake_loader)
        return stats

    return _configure


@pytest.fixture
def post_factory() -> Callable[..., Dict]:
    """Factory fixture to build customized announcement/event post records cleanly in tests."""
    counter = 200

    def _create_post(**overrides) -> Dict:
        nonlocal counter
        counter += 1
        base = {
            "id": counter,
            "title": f"إعلان تجريبي رقم {counter}",
            "summary": "ملخص الإعلان التجريبي للتأكد من عمل واجهة برمجة التطبيقات.",
            "category": "general",
            "publishedAt": f"2026-11-{(counter % 28) + 1:02d}T10:00:00Z",
            "eventDate": "",
            "imageUrl": "",
        }
        base.update(overrides)
        return base

    return _create_post


@pytest.fixture
def mock_posts_source(monkeypatch) -> Callable[[List[Dict]], Dict[str, int]]:
    """Helper fixture to stub `load_posts` and track invocation count."""
    def _configure(records: List[Dict]) -> Dict[str, int]:
        stats = {"calls": 0}

        def _fake_loader():
            stats["calls"] += 1
            return copy.deepcopy(records)

        monkeypatch.setattr(backend_app, "load_posts", _fake_loader, raising=False)
        return stats

    return _configure


@pytest.fixture
def form_factory() -> Callable[..., Dict]:
    """Factory fixture to build customized Google Forms config records cleanly in tests."""
    counter = 300

    def _create_form(**overrides) -> Dict:
        nonlocal counter
        counter += 1
        form_id = f"1FAIpQLScFormFactoryTest{counter}AbCdEf"
        base = {
            "id": counter,
            "formType": "feedback",
            "title": f"نموذج تفاعل تجريبي {counter}",
            "description": "وصف تجريبي لنموذج Google Forms المعتمد.",
            "embedUrl": f"https://docs.google.com/forms/d/e/{form_id}/viewform?embedded=true",
            "canonicalUrl": f"https://docs.google.com/forms/d/e/{form_id}/viewform",
            "provider": "google_forms",
            "formId": form_id,
            "active": True,
            "displayOrder": None,
        }
        base.update(overrides)
        return base

    return _create_form


@pytest.fixture
def mock_forms_source(monkeypatch) -> Callable[[List[Dict]], Dict[str, int]]:
    """Helper fixture to stub `load_forms` and track invocation count."""
    def _configure(records: List[Dict]) -> Dict[str, int]:
        stats = {"calls": 0}

        def _fake_loader():
            stats["calls"] += 1
            return copy.deepcopy(records)

        monkeypatch.setattr(backend_app, "load_forms", _fake_loader, raising=False)
        return stats

    return _configure
