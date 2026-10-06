"""End-to-end smoke test against a RUNNING Genomera API (Phase 25).

  SMOKE_USER=admin SMOKE_PASSWORD=... python -m scripts.smoke_test --base http://127.0.0.1:8000

Credentials come from the environment, never from this file. The run creates one test patient (and a VCF analysis, report
and notification-free workflow state) in the target database, so point it at staging or a fresh deployment, not at a
database holding real records. Each step checks the real response; the exit code is non-zero if any step fails.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--timeout", type=float, default=60)
    a = ap.parse_args()
    user, pw = os.environ.get("SMOKE_USER"), os.environ.get("SMOKE_PASSWORD")
    if not user or not pw:
        print("Set SMOKE_USER and SMOKE_PASSWORD in the environment.", file=sys.stderr)
        return 2
    c = httpx.Client(base_url=a.base, timeout=a.timeout)
    results = []
    ctx: dict = {}

    def step(name, fn):
        t = time.perf_counter()
        try:
            detail = fn()
            ok = True
        except AssertionError as ex:
            ok, detail = False, f"assertion failed: {ex}"
        except Exception as ex:  # noqa: BLE001
            ok, detail = False, f"{type(ex).__name__}: {ex}"
        ms = (time.perf_counter() - t) * 1000
        results.append((name, ok, ms, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name:<28} {ms:8.0f} ms  {detail or ''}")

    def H():
        return {"Authorization": f"Bearer {ctx['token']}"}

    def health():
        r = c.get("/health"); assert r.status_code == 200 and r.json()["status"] == "ok", r.text
        return f"graph nodes={r.json()['graph_nodes']}"

    def ready():
        r = c.get("/readiness"); assert r.status_code == 200, r.text
        return ",".join(f"{k}={'ok' if v['ok'] else 'FAIL'}" for k, v in r.json()["checks"].items())

    def login():
        r = c.post("/api/v1/auth/token", data={"username": user, "password": pw}); assert r.status_code == 200, r.status_code
        ctx["token"] = r.json()["access_token"]

    def patient():
        r = c.post("/api/v1/patients", json={"age_years": 9, "sex": "F", "state": "Andhra Pradesh", "community": "Reddy", "consanguineous": True}, headers=H())
        assert r.status_code == 200, r.text
        ctx["pid"] = r.json()["patient_id"]
        assert c.get(f"/api/v1/patients/{ctx['pid']}", headers=H()).status_code == 200
        return ctx["pid"]

    def case():
        items = [{"hpo_id": h, "assertion": "present"} for h in ("HP:0001337", "HP:0000952")]
        r = c.post(f"/api/v1/phenotype/case/{ctx['pid']}/import", json={"items": items}, headers=H()); assert r.status_code == 200, r.text
        r = c.get(f"/api/v1/phenotype/case/{ctx['pid']}", headers=H()); assert r.status_code == 200 and len(r.json()["observed"]) == 2

    def variant():
        vcf = (ROOT / "data" / "seeds" / "clinical_sample_trio.vcf").read_bytes()
        r = c.post("/api/v1/variants/upload", files={"file": ("trio.vcf", vcf)}, data={"patient_id": ctx["pid"]}, headers=H())
        assert r.status_code == 200, r.text
        ctx["analysis"] = r.json()["analysis_id"]
        return f"{r.json()['qc_metrics']['total_variants']} variants"

    def diagnosis():
        r = c.get(f"/api/v1/dx/case/{ctx['pid']}", headers=H()); assert r.status_code == 200 and r.json()["available"], r.text
        return r.json()["differential"][0]["disease_name"]

    def simple(path):
        def f():
            r = c.get(path.format(**ctx), headers=H()); assert r.status_code == 200, f"{r.status_code} {r.text[:120]}"
        return f

    def report():
        r = c.post(f"/api/v1/reports/case/{ctx['pid']}", json={}, headers=H()); assert r.status_code in (200, 201), r.text
        rid = r.json()["report_id"]
        p = c.get(f"/api/v1/reports/{rid}/pdf", headers=H()); assert p.status_code == 200 and p.content[:5] == b"%PDF-"
        return f"{rid}, pdf {len(p.content)} bytes"

    def search():
        r = c.get("/api/v1/search", params={"q": ctx["pid"]}, headers=H()); assert r.status_code == 200 and r.json()["results"]["cases"], r.text

    def assistant():
        r = c.post("/api/v1/assistant/chat", json={"message": "Summarise the key findings for this case.", "patient_id": ctx["pid"], "analysis_id": ctx["analysis"]}, headers=H())
        assert r.status_code == 200 and r.json().get("response"), r.text[:200]

    def metrics():
        r = c.get("/metrics", headers=H())
        assert r.status_code in (200, 403), r.status_code               # 403 for non-admin smoke users is expected
        return "admin" if r.status_code == 200 else "non-admin (forbidden, as designed)"

    for name, fn in (("health", health), ("readiness", ready), ("login", login), ("open patient", patient), ("case phenotypes", case),
                     ("variant analysis", variant), ("diagnosis", diagnosis), ("pgx", simple("/api/v1/pgx/case/{pid}")),
                     ("reproductive", simple("/api/v1/repro/case/{pid}")), ("digital twin", simple("/api/v1/digital-twin/{pid}")),
                     ("report + pdf", report), ("search", search), ("ai assistant", assistant), ("metrics", metrics)):
        step(name, fn)
        if name == "login" and not results[-1][1]:
            break
    failed = [n for n, ok, *_ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} steps passed" + (f"; FAILED: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
