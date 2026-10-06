"""Phase 21 measured performance baseline. Real requests through the ASGI app against a throwaway database.

  python -m scripts.perf_baseline [label]     writes docs/perf/<label>.json and prints a table
Numbers are wall-clock milliseconds on the machine that runs it (median of N, plus p95)."""
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")
os.environ["GENOMERA_RATE_LIMIT_OFF"] = "1"

ROOT = Path(__file__).resolve().parents[1]
API = "/api/v1"


def main(label: str = "baseline", n_patients: int = 600) -> dict:
    from fastapi.testclient import TestClient
    from backend.app import store
    from backend.app.hardening import limiter
    from backend.app.main import app
    from backend.app.security import hash_password

    tmp = Path(tempfile.mkdtemp()) / "perf.sqlite3"
    store.DB_PATH = tmp
    store.init_db()
    store.create_user("perf", "doctor", hash_password("perf-pass-123"))
    states = ["Kerala", "Tamil Nadu", "Gujarat", "Bihar", "Assam"]
    for i in range(n_patients):
        store.create_patient({"age_years": i % 80, "sex": "FM"[i % 2], "state": states[i % 5], "community": "Test"}, "perf")

    c = TestClient(app)
    tok = c.post(f"{API}/auth/token", data={"username": "perf", "password": "perf-pass-123"}).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    pid = store.list_patients(limit=1)[0]["patient_id"]
    vcf = (ROOT / "tests" / "data").glob("*.vcf")
    demo_vcf = c.get(f"{API}/variants/demo-vcf", headers=H)

    def reset():
        try:
            limiter.reset()
        except Exception:
            pass

    cases = [
        ("health", "GET", "/health", None),
        ("patients list (limit 500)", "GET", f"{API}/patients?limit=500", None),
        ("patients list (limit 50)", "GET", f"{API}/patients?limit=50", None),
        ("patient detail", "GET", f"{API}/patients/{pid}", None),
        ("global search", "GET", f"{API}/search?q=kerala", None),
        ("hpo search", "GET", f"{API}/phenotype/search?q=seizure", None),
        ("kg search", "GET", f"{API}/kg/search?q=wilson", None),
        ("kg stats", "GET", f"{API}/kg/stats", None),
        ("diagnosis", "POST", f"{API}/diagnosis", {"hpo_ids": ["HP:0001250", "HP:0001337"], "top_k": 5}),
        ("analytics overview", "GET", f"{API}/analytics/overview", None),
        ("digital twin", "GET", f"{API}/digital-twin/{pid}", None),
        ("notifications", "GET", f"{API}/workflow/notifications", None),
        ("workflow queue", "GET", f"{API}/workflow/queue", None),
        ("variant analyses list", "GET", f"{API}/variants/analyses", None),
        ("national dashboard", "GET", f"{API}/dashboard/national", None),
    ]
    out = {}
    for name, m, path, body in cases:
        times, status, size = [], None, 0
        for _ in range(7):
            reset()
            t = time.perf_counter()
            r = c.get(path, headers=H) if m == "GET" else c.post(path, json=body, headers=H)
            times.append((time.perf_counter() - t) * 1000)
            status, size = r.status_code, len(r.content)
        times.sort()
        out[name] = {"status": status, "median_ms": round(statistics.median(times), 1), "p95_ms": round(times[-2], 1), "bytes": size}
    # VCF analysis (write path) and report
    try:
        vtxt = demo_vcf.text if demo_vcf.status_code == 200 else None
        if vtxt:
            reset(); t = time.perf_counter()
            r = c.post(f"{API}/variants/upload", files={"file": ("demo.vcf", vtxt.encode(), "text/plain")}, headers=H)
            out["vcf upload+analysis"] = {"status": r.status_code, "median_ms": round((time.perf_counter() - t) * 1000, 1), "bytes": len(r.content)}
    except Exception as ex:  # noqa: BLE001
        out["vcf upload+analysis"] = {"status": "error", "note": type(ex).__name__}
    reset(); t = time.perf_counter()
    r = c.post(f"{API}/reports/case/{pid}", json={}, headers=H)
    out["report create"] = {"status": r.status_code, "median_ms": round((time.perf_counter() - t) * 1000, 1), "bytes": len(r.content)}
    if r.status_code == 200 and "report_id" in r.json():
        rid = r.json()["report_id"]
        t = time.perf_counter(); p = c.get(f"{API}/reports/{rid}/pdf", headers=H)
        out["report pdf"] = {"status": p.status_code, "median_ms": round((time.perf_counter() - t) * 1000, 1), "bytes": len(p.content)}

    dist = ROOT / "web" / "dist" / "assets"
    bundle = {f.name: f.stat().st_size for f in dist.glob("*")} if dist.exists() else "web/dist not built"
    res = {"label": label, "patients_seeded": n_patients, "endpoints": out, "bundle_bytes": bundle,
           "note": "Single local machine, TestClient (no network). Compare labels from the same machine only."}
    d = ROOT / "docs" / "perf"; d.mkdir(parents=True, exist_ok=True)
    (d / f"{label}.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    for k, v in out.items():
        print(f"{k:32} {v.get('status')!s:>4} {v.get('median_ms', '-')!s:>9} ms {v.get('bytes', 0):>9} B")
    print("bundle:", bundle)
    return res


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "baseline")
