"""Phase 25 observability: request IDs, structured logs, in-process metrics, readiness checks.

Everything reported here is measured at runtime. Metrics are per process and reset on restart (documented in
docs/DEPLOYMENT.md); there is no background-job system in Genomera, so no job metric is exported.

Logging never records request bodies, headers, query strings or user-supplied identifiers: only the matched route
template (e.g. /api/v1/patients/{patient_id}), method, status, duration and request id.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

LOG_FORMAT = os.environ.get("GENOMERA_LOG_FORMAT", "text").lower()          # json | text
LOG_LEVEL = os.environ.get("GENOMERA_LOG_LEVEL", "INFO").upper()
BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_ID_OK = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_BEARER = re.compile(r"(?i)(bearer|basic)\s+[A-Za-z0-9._~+/=-]+")
_SECRET = re.compile(r"(?i)(authorization|password|passwd|secret|api[_-]?key|token)(\"?\s*[:=]\s*\"?)([^\s\",;]+)")
START_TIME = time.time()

access_log = logging.getLogger("genomera.access")
error_log = logging.getLogger("genomera.error")


# ----------------------------------------------------------------------------- logging

class RedactingFilter(logging.Filter):
    """Last line of defence: masks anything that looks like a credential in any log message."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        masked = _SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}[redacted]", _BEARER.sub(lambda m: f"{m.group(1)} [redacted]", msg))
        if masked != msg:
            record.msg, record.args = masked, ()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
               "level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        extra = getattr(record, "fields", None)
        if extra:
            out.update(extra)
        if record.exc_info:
            out["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            out["stack"] = self.formatException(record.exc_info)       # server-side log only; never sent to clients
        return json.dumps(out, ensure_ascii=False, default=str)


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(LOG_LEVEL if LOG_LEVEL in logging._nameToLevel else "INFO")
    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter())
    handler.setFormatter(JsonFormatter() if LOG_FORMAT == "json" else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)


# ----------------------------------------------------------------------------- metrics

class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.requests: Dict[Tuple[str, str, int], int] = defaultdict(int)
            self.lat_buckets: Dict[Tuple[str, str], List[int]] = defaultdict(lambda: [0] * (len(BUCKETS) + 1))
            self.lat_sum: Dict[Tuple[str, str], float] = defaultdict(float)
            self.lat_count: Dict[Tuple[str, str], int] = defaultdict(int)
            self.in_flight = 0
            self.ai_requests = 0
            self.report_generations = 0
            self.unhandled_errors = 0

    def start(self) -> None:
        with self._lock:
            self.in_flight += 1

    def finish(self, method: str, route: str, status: int, seconds: float) -> None:
        with self._lock:
            self.in_flight -= 1
            self.requests[(method, route, status)] += 1
            key = (method, route)
            self.lat_sum[key] += seconds
            self.lat_count[key] += 1
            idx = next((i for i, b in enumerate(BUCKETS) if seconds <= b), len(BUCKETS))
            self.lat_buckets[key][idx] += 1
            if method == "POST" and route.startswith("/api/v1/assistant/chat"):
                self.ai_requests += 1
            if method == "POST" and route == "/api/v1/reports/case/{pid}":
                self.report_generations += 1
            if status >= 500:
                self.unhandled_errors += 1

    def snapshot(self) -> dict:
        with self._lock:
            total = sum(self.requests.values())
            errors = sum(v for (_, _, s), v in self.requests.items() if s >= 500)
            client_err = sum(v for (_, _, s), v in self.requests.items() if 400 <= s < 500)
            return {"requests_total": total, "server_errors_total": errors, "client_errors_total": client_err,
                    "server_error_rate": round(errors / total, 6) if total else None,
                    "in_flight": self.in_flight, "ai_requests_total": self.ai_requests,
                    "report_generations_total": self.report_generations, "uptime_seconds": round(time.time() - START_TIME, 1)}

    def prometheus(self, extra_gauges: Optional[Dict[str, float]] = None) -> str:
        lines = ["# HELP genomera_http_requests_total HTTP requests by method, route template and status.",
                 "# TYPE genomera_http_requests_total counter"]
        with self._lock:
            for (m, r, s), v in sorted(self.requests.items()):
                lines.append(f'genomera_http_requests_total{{method="{m}",route="{r}",status="{s}"}} {v}')
            lines += ["# HELP genomera_http_request_duration_seconds Request latency.", "# TYPE genomera_http_request_duration_seconds histogram"]
            for (m, r), counts in sorted(self.lat_buckets.items()):
                cum = 0
                for b, c in zip(BUCKETS, counts):
                    cum += c
                    lines.append(f'genomera_http_request_duration_seconds_bucket{{method="{m}",route="{r}",le="{b}"}} {cum}')
                cum += counts[-1]
                lines.append(f'genomera_http_request_duration_seconds_bucket{{method="{m}",route="{r}",le="+Inf"}} {cum}')
                lines.append(f'genomera_http_request_duration_seconds_sum{{method="{m}",route="{r}"}} {round(self.lat_sum[(m, r)], 6)}')
                lines.append(f'genomera_http_request_duration_seconds_count{{method="{m}",route="{r}"}} {self.lat_count[(m, r)]}')
            gauges = {"genomera_http_requests_in_flight": self.in_flight, "genomera_ai_requests_total": self.ai_requests,
                      "genomera_report_generations_total": self.report_generations, "genomera_unhandled_errors_total": self.unhandled_errors,
                      "genomera_uptime_seconds": round(time.time() - START_TIME, 1), **(extra_gauges or {})}
        for k, v in gauges.items():
            lines += [f"# TYPE {k} gauge", f"{k} {v}"]
        return "\n".join(lines) + "\n"


metrics = Metrics()


def system_resources() -> dict:
    """Real process/host numbers from psutil when installed; otherwise only what the standard library can measure."""
    out: dict = {"pid": os.getpid(), "threads": threading.active_count()}
    try:
        import psutil
        p = psutil.Process()
        out.update({"process_rss_bytes": p.memory_info().rss, "process_cpu_percent": p.cpu_percent(interval=None),
                    "host_cpu_percent": psutil.cpu_percent(interval=None), "host_memory_percent": psutil.virtual_memory().percent,
                    "open_files": len(p.open_files())})
    except Exception:  # noqa: BLE001
        out["note"] = "psutil not available: memory and CPU figures omitted"
    return out


# ----------------------------------------------------------------------------- readiness

def readiness(registry, store, migrations) -> Tuple[bool, dict]:
    """Real checks, each with its own result. Ready only if every check passes."""
    checks: Dict[str, dict] = {}
    t = time.perf_counter()
    try:
        with store._connect() as conn:
            conn.execute("SELECT 1").fetchone()
            pending = migrations.status(conn)["pending"]
        checks["database"] = {"ok": True, "latency_ms": round((time.perf_counter() - t) * 1000, 2)}
        checks["migrations"] = {"ok": not pending, "pending": pending}
    except Exception as ex:  # noqa: BLE001
        error_log.error("readiness: database check failed: %s", type(ex).__name__)
        checks["database"] = {"ok": False, "error": type(ex).__name__}
        checks["migrations"] = {"ok": False, "error": "database unavailable"}
    try:
        st = registry.status()
        checks["knowledge_graph"] = {"ok": st["graph_nodes"] > 0, "nodes": st["graph_nodes"], "edges": st["graph_edges"]}
    except Exception as ex:  # noqa: BLE001
        checks["knowledge_graph"] = {"ok": False, "error": type(ex).__name__}
    ok = all(c["ok"] for c in checks.values())
    return ok, {"status": "ready" if ok else "not_ready", "checks": checks}


# ----------------------------------------------------------------------------- middleware

class RequestObservabilityMiddleware:
    """Assigns/propagates X-Request-ID, times each request, logs one structured line, and records metrics.

    Unhandled exceptions are logged with their stack trace (server-side only) and answered with a generic 500 that carries
    only the request id, so failures can be diagnosed from logs without leaking internals to clients."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        inbound = headers.get(b"x-request-id", b"").decode("latin-1")
        rid = inbound if _ID_OK.match(inbound) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = rid
        method = scope["method"]
        started = time.perf_counter()
        state = {"status": 500, "sent": False}
        metrics.start()

        async def send_wrapped(message):
            if message["type"] == "http.response.start":
                state["status"], state["sent"] = message["status"], True
                message = {**message, "headers": [*message["headers"], (b"x-request-id", rid.encode())]}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapped)
        except Exception as ex:  # noqa: BLE001
            route = getattr(scope.get("route"), "path", None) or "unmatched"
            error_log.error("unhandled exception request_id=%s route=%s", rid, route, exc_info=True,
                            extra={"fields": {"request_id": rid, "route": route, "method": method}})
            if not state["sent"]:
                body = json.dumps({"detail": "Internal server error", "request_id": rid}).encode()
                state["status"] = 500
                await send_wrapped({"type": "http.response.start", "status": 500,
                                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
                await send({"type": "http.response.body", "body": body})
            else:
                raise
        finally:
            seconds = time.perf_counter() - started
            route = getattr(scope.get("route"), "path", None) or "unmatched"
            metrics.finish(method, route, state["status"], seconds)
            if route != "/health" or state["status"] >= 400:
                access_log.info("%s %s %s %.1fms", method, route, state["status"], seconds * 1000,
                                extra={"fields": {"request_id": rid, "method": method, "route": route, "status": state["status"],
                                                  "duration_ms": round(seconds * 1000, 2)}})
