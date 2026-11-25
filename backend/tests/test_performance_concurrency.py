from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import subprocess
import sys
import threading

import cv2
import numpy as np
import pytest
from werkzeug.security import generate_password_hash

import app as backend_app

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
_BENCH_PW = "MahjarBench!2026"
_BENCH_PW_HASH = generate_password_hash(_BENCH_PW)


def _make_png_bytes(width: int = 48, height: int = 48, color=(30, 110, 190)) -> bytes:
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :] = color
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


@pytest.mark.unit
@pytest.mark.performance
class TestCacheThreadSafetyAndBounds:
    """Thread-safety, cold-cache stampede protection, and memory bounds under free-tier limits."""

    def test_cold_cache_stampede_protection_across_public_endpoints(
        self,
        flask_app,
        mock_committee_source,
        mock_posts_source,
        mock_forms_source,
        member_factory,
        post_factory,
        form_factory,
    ):
        committee_stats = mock_committee_source([member_factory()])
        posts_stats = mock_posts_source([post_factory()])
        forms_stats = mock_forms_source([form_factory()])

        backend_app.clear_committee_cache()
        backend_app.clear_posts_cache()
        backend_app.clear_forms_cache()

        num_threads = 50

        for path, stats in (
            ("/api/committee", committee_stats),
            ("/api/posts", posts_stats),
            ("/api/forms", forms_stats),
        ):
            barrier = threading.Barrier(num_threads)

            def _hit(_idx):
                with flask_app.test_client() as local_client:
                    barrier.wait(timeout=5.0)
                    resp = local_client.get(path)
                    return resp.status_code, resp.get_json()

            with ThreadPoolExecutor(max_workers=num_threads) as pool:
                results = list(pool.map(_hit, range(num_threads)))

            assert len(results) == num_threads
            assert all(code == 200 and isinstance(body, list) for code, body in results)
            assert stats["calls"] == 1, f"Expected single loader call on {path}, got {stats['calls']}"

    def test_concurrent_reads_with_admin_mutations_and_cache_invalidation_produce_zero_5xx(
        self, flask_app, admin_auth_headers
    ):
        stop_event = threading.Event()
        errors = []
        read_count = {"count": 0}
        count_lock = threading.Lock()

        def _reader(worker_id: int):
            routes = ("/api/committee", "/api/posts", "/api/forms")
            with flask_app.test_client() as local_client:
                i = 0
                while not stop_event.is_set():
                    path = routes[(worker_id + i) % len(routes)]
                    try:
                        resp = local_client.get(path)
                        if resp.status_code >= 500 or resp.status_code != 200:
                            errors.append(f"Reader {path} status={resp.status_code}")
                        _ = resp.get_json()
                    except Exception as exc:
                        errors.append(f"Reader exception on {path}: {exc!r}")
                    with count_lock:
                        read_count["count"] += 1
                    i += 1

        def _writer():
            with flask_app.test_client() as admin_client:
                for step in range(15):
                    try:
                        resp = admin_client.post(
                            "/api/admin/posts",
                            headers=admin_auth_headers,
                            json={
                                "title": f"منشور تزامن {step}",
                                "summary": "اختبار مسح الكاش أثناء القراءة المتزامنة.",
                                "category": "updates",
                            },
                        )
                        if resp.status_code != 201:
                            errors.append(f"Writer POST status={resp.status_code}")
                        backend_app.clear_committee_cache()
                        backend_app.clear_forms_cache()
                    except Exception as exc:
                        errors.append(f"Writer exception: {exc!r}")
            stop_event.set()

        with ThreadPoolExecutor(max_workers=17) as pool:
            reader_futures = [pool.submit(_reader, idx) for idx in range(16)]
            writer_future = pool.submit(_writer)
            writer_future.result(timeout=15.0)
            for fut in reader_futures:
                fut.result(timeout=15.0)

        assert read_count["count"] > 50
        assert errors == []

    def test_response_cache_is_bounded_for_free_tier_ram(self, client):
        max_entries = backend_app.MAX_CACHE_RESPONSE_ENTRIES
        assert 32 <= max_entries <= 512

        for idx in range(max_entries + 40):
            resp = client.get(f"/api/posts?limit={(idx % 50) + 1}&offset={idx}")
            assert resp.status_code == 200

        assert len(backend_app._posts_cache["responses"]) <= max_entries


@pytest.mark.unit
class TestLoadBenchmarkEngine:
    """Unit tests for latency percentile calculations and NFR threshold evaluation."""

    def test_compute_latency_metrics_and_evaluate_nfr_thresholds(self):
        import load_benchmark

        samples = [
            {"endpoint": "/api/posts", "status": 200, "latencyMs": 10.0, "error": None},
            {"endpoint": "/api/posts", "status": 200, "latencyMs": 20.0, "error": None},
            {"endpoint": "/api/committee", "status": 200, "latencyMs": 30.0, "error": None},
            {"endpoint": "/api/forms", "status": 304, "latencyMs": 40.0, "error": None},
            {"endpoint": "/api/health", "status": 200, "latencyMs": 100.0, "error": None},
        ]
        metrics = load_benchmark.compute_latency_metrics(
            samples,
            elapsed_seconds=0.25,
            peak_rss_mb=120.0,
            peak_tracemalloc_mb=4.5,
        )
        assert metrics["totalRequests"] == 5
        assert metrics["successfulRequests"] == 5
        assert metrics["clientErrors4xx"] == 0
        assert metrics["serverErrors5xx"] == 0
        assert metrics["connectionErrors"] == 0
        assert metrics["minMs"] == 10.0
        assert metrics["avgMs"] == 40.0
        assert metrics["p50Ms"] == 30.0
        assert metrics["maxMs"] == 100.0
        assert metrics["requestsPerSec"] == 20.0
        assert metrics["peakRssMb"] == 120.0

        passed = load_benchmark.evaluate_nfr_thresholds(
            metrics, max_avg_ms=500.0, max_rss_mb=512.0
        )
        assert passed["passed"] is True
        assert passed["failures"] == []

        failing_metrics = {
            **metrics,
            "avgMs": 512.4,
            "serverErrors5xx": 2,
            "connectionErrors": 1,
            "peakRssMb": 600.0,
        }
        failed = load_benchmark.evaluate_nfr_thresholds(
            failing_metrics, max_avg_ms=500.0, max_rss_mb=512.0
        )
        assert failed["passed"] is False
        assert len(failed["failures"]) == 4


@pytest.mark.performance
class TestFiveHundredConcurrentUsersFreeTier:
    """Live TCP/HTTP concurrency benchmarks simulating 500 concurrent users under free-tier limits."""

    def _build_prod_sqlite_app(self, tmp_path):
        data_dir = tmp_path / "bench_data"
        dist_dir = tmp_path / "dist"
        (dist_dir / "assets").mkdir(parents=True)
        (dist_dir / "index.html").write_text(
            '<!doctype html><html lang="ar" dir="rtl"><body><div id="root"></div></body></html>',
            encoding="utf-8",
        )
        (dist_dir / "assets" / "app-bench.js").write_text(
            "console.log('mahjar');", encoding="utf-8"
        )

        pw = _BENCH_PW
        prod_app = backend_app.create_app({
            "TESTING": True,
            "MAHJAR_ENV": "production",
            "SECRET_KEY": "b" * 48,
            "ADMIN_USERNAME": "admin",
            "ADMIN_PASSWORD_HASH": _BENCH_PW_HASH,
            "ENFORCE_HTTPS": True,
            "TRUST_PROXY_COUNT": 1,
            "CORS_ALLOWED_ORIGINS": ("https://mahjar-parents.vercel.app",),
            "DATA_DIR": str(data_dir),
            "STORAGE_BACKEND": "sqlite",
            "CMS_DATA_FILE": str(data_dir / "cms_data.sqlite3"),
            "MEDIA_UPLOAD_DIR": str(data_dir / "uploads" / "images"),
            "SERVE_FRONTEND_DIST": True,
            "FRONTEND_DIST_DIR": str(dist_dir),
        })

        with prod_app.test_client() as c:
            login = c.post(
                "/api/admin/auth/login",
                headers={"X-Forwarded-Proto": "https"},
                json={"username": "admin", "password": pw},
            )
            assert login.status_code == 200
            token = login.get_json()["token"]

            upload = c.post(
                "/api/media/images",
                headers={
                    "X-Forwarded-Proto": "https",
                    "Authorization": f"Bearer {token}",
                },
                data={"file": (io.BytesIO(_make_png_bytes()), "banner.png", "image/png")},
                content_type="multipart/form-data",
            )
            assert upload.status_code == 201
            image_url = upload.get_json()["url"]

        return prod_app, image_url, token

    def test_500_concurrent_users_burst_under_500ms_and_zero_5xx(self, tmp_path):
        import load_benchmark

        prod_app, image_url, _token = self._build_prod_sqlite_app(tmp_path)

        report = load_benchmark.run_http_load_benchmark(
            prod_app,
            concurrent_users=500,
            requests_per_user=1,
            server_threads=8,
            use_barrier=True,
            extra_endpoints=[image_url, "/"],
            headers={"X-Forwarded-Proto": "https"},
            max_avg_ms=500.0,
            max_rss_mb=512.0,
        )

        metrics = report["metrics"]
        assert metrics["totalRequests"] == 500
        assert metrics["serverErrors5xx"] == 0
        assert metrics["connectionErrors"] == 0
        assert metrics["clientErrors4xx"] == 0
        assert metrics["avgMs"] < 500.0
        assert metrics["p95Ms"] < 1000.0
        assert metrics["peakRssMb"] < 512.0
        assert report["nfr"]["passed"] is True
        assert image_url in report["byEndpoint"]
        assert "/api/posts" in report["byEndpoint"]
        assert "/api/committee" in report["byEndpoint"]
        assert "/api/forms" in report["byEndpoint"]

    def test_500_concurrent_users_sustained_wave_with_etag_304(self, tmp_path):
        import load_benchmark

        prod_app, image_url, _token = self._build_prod_sqlite_app(tmp_path)

        report = load_benchmark.run_http_load_benchmark(
            prod_app,
            concurrent_users=500,
            requests_per_user=2,
            server_threads=8,
            use_barrier=True,
            include_conditional_etag=True,
            extra_endpoints=[image_url],
            headers={"X-Forwarded-Proto": "https"},
            max_avg_ms=500.0,
            max_rss_mb=512.0,
        )

        metrics = report["metrics"]
        assert metrics["totalRequests"] == 1000
        assert metrics["serverErrors5xx"] == 0
        assert metrics["connectionErrors"] == 0
        assert metrics["avgMs"] < 500.0
        assert metrics["statusCodes"].get(304, 0) > 0
        assert report["nfr"]["passed"] is True

    def test_concurrent_public_reads_with_live_sqlite_admin_writes(self, tmp_path):
        import load_benchmark

        prod_app, _image_url, token = self._build_prod_sqlite_app(tmp_path)

        rw_report = load_benchmark.run_mixed_read_write_benchmark(
            prod_app,
            admin_token=token,
            reader_users=100,
            requests_per_reader=2,
            writer_ops=8,
            server_threads=8,
            headers={"X-Forwarded-Proto": "https"},
        )

        assert rw_report["readers"]["serverErrors5xx"] == 0
        assert rw_report["readers"]["connectionErrors"] == 0
        assert rw_report["readers"]["avgMs"] < 500.0
        assert rw_report["writers"]["serverErrors5xx"] == 0
        assert rw_report["writers"]["connectionErrors"] == 0
        assert rw_report["writers"]["successes"] == 8

    def test_cli_load_benchmark_runs_500_users_and_writes_json_report(self, tmp_path):
        json_out = tmp_path / "bench_report.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(BACKEND_DIR / "load_benchmark.py"),
                "--users",
                "500",
                "--requests-per-user",
                "1",
                "--storage",
                "sqlite",
                "--json-out",
                str(json_out),
            ],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, f"CLI failed:\n{proc.stdout}\n{proc.stderr}"
        assert json_out.is_file()
        payload = json.loads(json_out.read_text(encoding="utf-8"))
        assert payload["nfr"]["passed"] is True
        assert payload["metrics"]["totalRequests"] == 500
        assert payload["metrics"]["serverErrors5xx"] == 0
        assert payload["metrics"]["avgMs"] < 500.0
