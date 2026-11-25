"""Free-tier HTTP concurrency & latency load benchmark runner for Mahjar Parents.

Simulates up to 500+ concurrent users against a bounded single-process
multi-threaded WSGI server mirroring free-tier PaaS resource constraints
(1 worker, 8 threads, 512 MB RAM ceiling, SQLite WAL / JSON persistence,
and OpenCV-processed image assets).
"""

from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import http.client
import io
import json
import math
import multiprocessing
import os
from pathlib import Path
import resource
import sys
import tempfile
import threading
import time
import tracemalloc
from typing import Any, Sequence
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer

from werkzeug.security import generate_password_hash

_BACKEND_DIR = str(Path(__file__).resolve().parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

DEFAULT_PUBLIC_SCENARIO: tuple[str, ...] = (
    "/api/posts",
    "/api/posts?category=upcoming_event&limit=10",
    "/api/committee",
    "/api/forms",
    "/api/posts",
    "/api/committee",
    "/api/health",
)


class _NullTextStream:
    """Thread-safe no-op text stream avoiding sys.stderr capture lock contention."""

    def write(self, _data: str) -> int:
        return 0

    def flush(self) -> None:
        return


_NULL_STDERR = _NullTextStream()


class QuietWSGIRequestHandler(WSGIRequestHandler):
    """Lightweight stdlib WSGI handler suppressing logs/DNS lookups without dev drain sleeps."""

    wbufsize = -1

    def address_string(self) -> str:
        return self.client_address[0] if self.client_address else "127.0.0.1"

    def get_stderr(self) -> Any:
        return _NULL_STDERR

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return


class BoundedThreadPoolWSGIServer(WSGIServer):
    """WSGI server backed by a fixed-size thread pool matching Gunicorn gthread limits."""

    allow_reuse_address = True
    request_queue_size = 512

    def __init__(
        self,
        host: str,
        port: int,
        app: Any,
        *,
        server_threads: int = 8,
    ) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(server_threads)),
            thread_name_prefix="wsgi-worker",
        )
        super().__init__((host, port), QuietWSGIRequestHandler)
        self.set_app(app)

    def process_request(self, request: Any, client_address: Any) -> None:
        try:
            self._executor.submit(self._handle_request_safe, request, client_address)
        except RuntimeError:
            self.close_request(request)

    def _handle_request_safe(self, request: Any, client_address: Any) -> None:
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)

    def server_close(self) -> None:
        try:
            super().server_close()
        finally:
            self._executor.shutdown(wait=True)


@contextmanager
def LiveBenchmarkServer(
    wsgi_app: Any,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    server_threads: int = 8,
):
    """Context manager running BoundedThreadPoolWSGIServer on a loopback port."""
    server = BoundedThreadPoolWSGIServer(
        host, port, wsgi_app, server_threads=server_threads
    )
    bound_host, bound_port = server.server_address[:2]
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.05},
        daemon=True,
        name="benchmark-http-server",
    )
    thread.start()
    try:
        yield bound_host, int(bound_port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return round(sorted_values[0], 2)
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return round(sorted_values[lower], 2)
    weight = rank - lower
    interpolated = sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight
    return round(interpolated, 2)


def _get_peak_rss_mb() -> float:
    usage_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return round(usage_kb / (1024.0 * 1024.0), 2)
    return round(usage_kb / 1024.0, 2)


def compute_latency_metrics(
    samples: Sequence[dict[str, Any]],
    *,
    elapsed_seconds: float,
    peak_rss_mb: float = 0.0,
    peak_tracemalloc_mb: float = 0.0,
) -> dict[str, Any]:
    """Compute latency percentiles, status histogram, error counts, and throughput."""
    total = len(samples)
    latencies = sorted(
        float(s["latencyMs"])
        for s in samples
        if s.get("error") is None and s.get("latencyMs") is not None
    )
    status_codes: dict[int, int] = {}
    successful = 0
    client_errors_4xx = 0
    server_errors_5xx = 0
    connection_errors = 0

    for sample in samples:
        if sample.get("error") is not None or sample.get("status") is None:
            connection_errors += 1
            continue
        code = int(sample["status"])
        status_codes[code] = status_codes.get(code, 0) + 1
        if 200 <= code < 400:
            successful += 1
        elif 400 <= code < 500:
            client_errors_4xx += 1
        elif code >= 500:
            server_errors_5xx += 1

    avg_ms = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
    safe_elapsed = max(float(elapsed_seconds), 1e-6)
    rps = round(total / safe_elapsed, 2)

    return {
        "totalRequests": total,
        "successfulRequests": successful,
        "clientErrors4xx": client_errors_4xx,
        "serverErrors5xx": server_errors_5xx,
        "connectionErrors": connection_errors,
        "statusCodes": status_codes,
        "elapsedSeconds": round(safe_elapsed, 3),
        "requestsPerSec": rps,
        "minMs": round(latencies[0], 2) if latencies else 0.0,
        "avgMs": avg_ms,
        "p50Ms": _percentile(latencies, 50.0),
        "p95Ms": _percentile(latencies, 95.0),
        "p99Ms": _percentile(latencies, 99.0),
        "maxMs": round(latencies[-1], 2) if latencies else 0.0,
        "peakRssMb": round(float(peak_rss_mb), 2),
        "peakTracemallocMb": round(float(peak_tracemalloc_mb), 2),
    }


def evaluate_nfr_thresholds(
    metrics: dict[str, Any],
    *,
    max_avg_ms: float = 550.0,
    max_rss_mb: float = 512.0,
) -> dict[str, Any]:
    """Evaluate SRS 5.1 / Task 3.2.2 acceptance thresholds against observed metrics."""
    failures: list[str] = []
    if metrics["avgMs"] >= max_avg_ms:
        failures.append(
            f"Average latency {metrics['avgMs']}ms >= {max_avg_ms}ms threshold"
        )
    if metrics["serverErrors5xx"] > 0:
        failures.append(
            f"Observed {metrics['serverErrors5xx']} server 5xx errors (expected 0)"
        )
    if metrics["connectionErrors"] > 0:
        failures.append(
            f"Observed {metrics['connectionErrors']} connection errors (expected 0)"
        )
    if metrics["peakRssMb"] >= max_rss_mb:
        failures.append(
            f"Peak RSS memory {metrics['peakRssMb']} MB >= {max_rss_mb} MB limit"
        )

    return {
        "passed": len(failures) == 0,
        "maxAvgMs": max_avg_ms,
        "maxRssMb": max_rss_mb,
        "failures": failures,
    }


def _http_get(
    host: str,
    port: int,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_s: float = 10.0,
) -> tuple[int | None, dict[str, str], float, str | None]:
    req_headers = {"Connection": "close"}
    if headers:
        req_headers.update(headers)
    start = time.perf_counter()
    conn: http.client.HTTPConnection | None = None
    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout_s)
        conn.request("GET", path, headers=req_headers)
        resp = conn.getresponse()
        resp.read()
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        resp_headers = {k.lower(): v for k, v in resp.getheaders()}
        return resp.status, resp_headers, elapsed_ms, None
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return None, {}, elapsed_ms, repr(exc)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _http_json_write(
    host: str,
    port: int,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    *,
    headers: dict[str, str] | None = None,
    timeout_s: float = 10.0,
) -> tuple[int | None, Any, float, str | None]:
    req_headers = {"Connection": "close"}
    if headers:
        req_headers.update(headers)
    body_bytes = None
    if payload is not None:
        req_headers["Content-Type"] = "application/json"
        body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    start = time.perf_counter()
    conn: http.client.HTTPConnection | None = None
    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout_s)
        conn.request(method, path, body=body_bytes, headers=req_headers)
        resp = conn.getresponse()
        raw = resp.read()
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        parsed = json.loads(raw.decode("utf-8")) if raw else None
        return resp.status, parsed, elapsed_ms, None
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return None, None, elapsed_ms, repr(exc)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _async_client_process_entry(
    host: str,
    port: int,
    route_mix: list[str],
    concurrent_users: int,
    requests_per_user: int,
    headers: dict[str, str],
    include_conditional_etag: bool,
    etag_by_route: dict[str, str],
    timeout_s: float,
    result_queue: Any,
) -> None:
    """Drive N concurrent asyncio HTTP clients from an isolated OS process (no server GIL contention)."""

    async def _run() -> tuple[float, list[dict[str, Any]]]:
        async def _send_one(route: str, extra_headers: dict[str, str]) -> tuple[int | None, float, str | None]:
            req_lines = [
                f"GET {route} HTTP/1.1",
                f"Host: {host}:{port}",
                "Connection: close",
            ]
            for k, v in extra_headers.items():
                req_lines.append(f"{k}: {v}")
            raw_req = ("\r\n".join(req_lines) + "\r\n\r\n").encode("latin1")

            t0 = time.perf_counter()
            writer = None
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=timeout_s,
                )
                writer.write(raw_req)
                await asyncio.wait_for(writer.drain(), timeout=timeout_s)
                status_line = await asyncio.wait_for(reader.readline(), timeout=timeout_s)
                await asyncio.wait_for(reader.read(), timeout=timeout_s)
                latency_ms = (time.perf_counter() - t0) * 1000.0
                parts = status_line.split(b" ", 2)
                status_code = int(parts[1]) if len(parts) >= 2 else None
                return status_code, latency_ms, None
            except Exception as exc:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                return None, latency_ms, repr(exc)
            finally:
                if writer is not None:
                    try:
                        writer.close()
                        await writer.wait_closed()
                    except Exception:
                        pass

        async def _send_user_request(user_idx: int, req_idx: int) -> dict[str, Any]:
            route = route_mix[(user_idx + req_idx) % len(route_mix)]
            req_headers = dict(headers)
            if (
                include_conditional_etag
                and req_idx > 0
                and route in etag_by_route
            ):
                req_headers["If-None-Match"] = etag_by_route[route]
            status, latency_ms, err = await _send_one(route, req_headers)
            return {
                "endpoint": route,
                "status": status,
                "latencyMs": latency_ms,
                "error": err,
            }

        wall_start = time.perf_counter()
        flat_samples: list[dict[str, Any]] = []
        for req_idx in range(requests_per_user):
            wave_samples = await asyncio.gather(
                *(_send_user_request(idx, req_idx) for idx in range(concurrent_users))
            )
            flat_samples.extend(wave_samples)
        wall_elapsed = time.perf_counter() - wall_start
        return wall_elapsed, flat_samples

    elapsed, samples = asyncio.run(_run())
    result_queue.put((elapsed, samples))


def run_http_load_benchmark(
    wsgi_app: Any,
    *,
    concurrent_users: int = 500,
    requests_per_user: int = 1,
    server_threads: int = 8,
    endpoints: Sequence[str] | None = None,
    extra_endpoints: Sequence[str] | None = None,
    headers: dict[str, str] | None = None,
    use_barrier: bool = True,
    include_conditional_etag: bool = False,
    timeout_s: float = 10.0,
    max_avg_ms: float = 550.0,
    max_rss_mb: float = 512.0,
    trace_memory: bool = False,
) -> dict[str, Any]:
    """Run an end-to-end concurrent HTTP load benchmark against a live Flask WSGI server."""
    route_mix = list(endpoints or DEFAULT_PUBLIC_SCENARIO)
    if extra_endpoints:
        route_mix.extend(extra_endpoints)
    if not route_mix:
        raise ValueError("At least one endpoint must be provided for benchmarking.")

    if trace_memory:
        tracemalloc.start()

    req_headers = dict(headers or {})
    samples: list[dict[str, Any]] = []
    wall_elapsed = 0.0

    with LiveBenchmarkServer(wsgi_app, server_threads=server_threads) as (host, port):
        etag_by_route: dict[str, str] = {}
        for route in set(route_mix):
            status, resp_headers, _, _ = _http_get(
                host, port, route, headers=req_headers, timeout_s=timeout_s
            )
            if include_conditional_etag and status == 200 and "etag" in resp_headers:
                etag_by_route[route] = resp_headers["etag"]

        # Spawn a dedicated load-generator process so 500 client sockets do not
        # contend on the single Python GIL with the 8-thread Flask WSGI server.
        ctx = multiprocessing.get_context("spawn")
        result_queue = ctx.Queue()
        client_proc = ctx.Process(
            target=_async_client_process_entry,
            args=(
                host,
                port,
                route_mix,
                concurrent_users,
                requests_per_user,
                req_headers,
                include_conditional_etag,
                etag_by_route,
                timeout_s,
                result_queue,
            ),
        )
        client_proc.start()
        try:
            wall_elapsed, samples = result_queue.get(
                timeout=max(30.0, timeout_s * requests_per_user + 15.0)
            )
        finally:
            client_proc.join(timeout=10.0)
            if client_proc.is_alive():
                client_proc.terminate()
                client_proc.join(timeout=5.0)

    if trace_memory:
        _current_mem, peak_trace_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_tracemalloc_mb = round(peak_trace_bytes / (1024.0 * 1024.0), 2)
    else:
        peak_tracemalloc_mb = 0.0
    peak_rss_mb = _get_peak_rss_mb()

    metrics = compute_latency_metrics(
        samples,
        elapsed_seconds=wall_elapsed,
        peak_rss_mb=peak_rss_mb,
        peak_tracemalloc_mb=peak_tracemalloc_mb,
    )
    nfr = evaluate_nfr_thresholds(
        metrics, max_avg_ms=max_avg_ms, max_rss_mb=max_rss_mb
    )

    by_endpoint_samples: dict[str, list[dict[str, Any]]] = {}
    for sample in samples:
        by_endpoint_samples.setdefault(sample["endpoint"], []).append(sample)

    by_endpoint = {
        ep: compute_latency_metrics(
            ep_samples,
            elapsed_seconds=wall_elapsed,
            peak_rss_mb=peak_rss_mb,
            peak_tracemalloc_mb=peak_tracemalloc_mb,
        )
        for ep, ep_samples in sorted(by_endpoint_samples.items())
    }

    return {
        "config": {
            "concurrentUsers": concurrent_users,
            "requestsPerUser": requests_per_user,
            "serverThreads": server_threads,
            "useBarrier": use_barrier,
            "includeConditionalEtag": include_conditional_etag,
        },
        "metrics": metrics,
        "byEndpoint": by_endpoint,
        "nfr": nfr,
    }


def run_mixed_read_write_benchmark(
    wsgi_app: Any,
    *,
    admin_token: str,
    reader_users: int = 100,
    requests_per_reader: int = 2,
    writer_ops: int = 8,
    server_threads: int = 8,
    headers: dict[str, str] | None = None,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    """Run concurrent public HTTP reads simultaneously with Admin SQLite writes."""
    reader_routes = ("/api/committee", "/api/posts", "/api/forms")
    reader_samples: list[dict[str, Any]] = []
    reader_lock = threading.Lock()
    writer_results: list[dict[str, Any]] = []
    start_barrier = threading.Barrier(reader_users + 1)

    with LiveBenchmarkServer(wsgi_app, server_threads=server_threads) as (host, port):
        def _reader(user_idx: int) -> None:
            local: list[dict[str, Any]] = []
            start_barrier.wait(timeout=30.0)
            for req_idx in range(requests_per_reader):
                route = reader_routes[(user_idx + req_idx) % len(reader_routes)]
                status, _h, latency_ms, err = _http_get(
                    host, port, route, headers=headers, timeout_s=timeout_s
                )
                local.append({
                    "endpoint": route,
                    "status": status,
                    "latencyMs": latency_ms,
                    "error": err,
                })
            with reader_lock:
                reader_samples.extend(local)

        def _writer() -> None:
            auth_headers = dict(headers or {})
            auth_headers["Authorization"] = f"Bearer {admin_token}"
            start_barrier.wait(timeout=30.0)
            for step in range(writer_ops):
                status, body, latency_ms, err = _http_json_write(
                    host,
                    port,
                    "POST",
                    "/api/admin/posts",
                    {
                        "title": f"تحديث تزامن {step}",
                        "summary": "اختبار كتابة SQLite متزامن مع القراءة.",
                        "category": "updates",
                    },
                    headers=auth_headers,
                    timeout_s=timeout_s,
                )
                writer_results.append({
                    "step": step,
                    "status": status,
                    "latencyMs": latency_ms,
                    "error": err,
                    "id": body.get("id") if isinstance(body, dict) else None,
                })

        wall_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=reader_users + 1) as pool:
            reader_futs = [pool.submit(_reader, idx) for idx in range(reader_users)]
            writer_fut = pool.submit(_writer)
            writer_fut.result(timeout=30.0)
            for fut in reader_futs:
                fut.result(timeout=30.0)
        wall_elapsed = time.perf_counter() - wall_start

    reader_metrics = compute_latency_metrics(
        reader_samples,
        elapsed_seconds=wall_elapsed,
        peak_rss_mb=_get_peak_rss_mb(),
    )
    writer_5xx = sum(
        1 for w in writer_results if w["status"] is not None and w["status"] >= 500
    )
    writer_conn_err = sum(1 for w in writer_results if w["error"] is not None)
    writer_ok = sum(1 for w in writer_results if w["status"] == 201)

    return {
        "readers": reader_metrics,
        "writers": {
            "total": len(writer_results),
            "successes": writer_ok,
            "serverErrors5xx": writer_5xx,
            "connectionErrors": writer_conn_err,
        },
    }


def _create_benchmark_app(tmp_dir: Path, storage_backend: str) -> tuple[Any, str]:
    import app as backend_app
    import cv2
    import numpy as np

    data_dir = tmp_dir / "data"
    dist_dir = tmp_dir / "dist"
    (dist_dir / "assets").mkdir(parents=True, exist_ok=True)
    (dist_dir / "index.html").write_text(
        '<!doctype html><html lang="ar" dir="rtl"><body><div id="root"></div></body></html>',
        encoding="utf-8",
    )

    pw = "MahjarCliBench!2026"
    ext = "sqlite3" if storage_backend == "sqlite" else "json"
    bench_app = backend_app.create_app({
        "TESTING": True,
        "MAHJAR_ENV": "production",
        "SECRET_KEY": "c" * 48,
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD_HASH": generate_password_hash(pw),
        "ENFORCE_HTTPS": True,
        "TRUST_PROXY_COUNT": 1,
        "CORS_ALLOWED_ORIGINS": ("https://mahjar-parents.vercel.app",),
        "DATA_DIR": str(data_dir),
        "STORAGE_BACKEND": storage_backend,
        "CMS_DATA_FILE": str(data_dir / f"cms_data.{ext}"),
        "MEDIA_UPLOAD_DIR": str(data_dir / "uploads" / "images"),
        "SERVE_FRONTEND_DIST": True,
        "FRONTEND_DIST_DIR": str(dist_dir),
    })

    img = np.zeros((64, 64, 3), dtype=np.uint8)
    img[:, :] = (30, 120, 200)
    ok, png_buf = cv2.imencode(".png", img)
    assert ok

    with bench_app.test_client() as client:
        login_resp = client.post(
            "/api/admin/auth/login",
            headers={"X-Forwarded-Proto": "https"},
            json={"username": "admin", "password": pw},
        )
        token = login_resp.get_json()["token"]
        upload_resp = client.post(
            "/api/media/images",
            headers={
                "X-Forwarded-Proto": "https",
                "Authorization": f"Bearer {token}",
            },
            data={"file": (io.BytesIO(png_buf.tobytes()), "bench.png", "image/png")},
            content_type="multipart/form-data",
        )
        image_url = upload_resp.get_json()["url"]

    return bench_app, image_url


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run free-tier HTTP concurrency & latency benchmark for Mahjar Parents."
    )
    parser.add_argument("--users", type=int, default=500)
    parser.add_argument("--requests-per-user", type=int, default=1)
    parser.add_argument("--server-threads", type=int, default=8)
    parser.add_argument("--storage", choices=("sqlite", "json"), default="sqlite")
    parser.add_argument("--max-avg-ms", type=float, default=550.0)
    parser.add_argument("--max-rss-mb", type=float, default=512.0)
    parser.add_argument("--json-out", type=str, default="")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="mahjar-bench-") as tmp:
        bench_app, image_url = _create_benchmark_app(Path(tmp), args.storage)
        report = run_http_load_benchmark(
            bench_app,
            concurrent_users=args.users,
            requests_per_user=args.requests_per_user,
            server_threads=args.server_threads,
            use_barrier=True,
            extra_endpoints=[image_url, "/"],
            headers={"X-Forwarded-Proto": "https"},
            max_avg_ms=args.max_avg_ms,
            max_rss_mb=args.max_rss_mb,
        )

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    m = report["metrics"]
    nfr = report["nfr"]
    print(
        f"Mahjar Parents Load Benchmark | users={args.users} reqs={m['totalRequests']} "
        f"threads={args.server_threads} storage={args.storage}\n"
        f"  Latency (ms): min={m['minMs']} avg={m['avgMs']} p50={m['p50Ms']} "
        f"p95={m['p95Ms']} p99={m['p99Ms']} max={m['maxMs']}\n"
        f"  Throughput:   {m['requestsPerSec']} req/s | elapsed={m['elapsedSeconds']}s\n"
        f"  Errors:       5xx={m['serverErrors5xx']} 4xx={m['clientErrors4xx']} conn={m['connectionErrors']}\n"
        f"  Memory:       peak_rss={m['peakRssMb']} MB (limit {args.max_rss_mb} MB)\n"
        f"  NFR Result:   {'PASS' if nfr['passed'] else 'FAIL'}"
    )
    if not nfr["passed"]:
        for reason in nfr["failures"]:
            print(f"  - {reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
