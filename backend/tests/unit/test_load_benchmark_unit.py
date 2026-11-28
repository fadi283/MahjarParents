import pytest


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
            metrics, max_avg_ms=550.0, max_rss_mb=512.0
        )
        assert passed["passed"] is True
        assert passed["failures"] == []

        failing_metrics = {
            **metrics,
            "avgMs": 560.4,
            "serverErrors5xx": 2,
            "connectionErrors": 1,
            "peakRssMb": 600.0,
        }
        failed = load_benchmark.evaluate_nfr_thresholds(
            failing_metrics, max_avg_ms=550.0, max_rss_mb=512.0
        )
        assert failed["passed"] is False
        assert len(failed["failures"]) == 4

