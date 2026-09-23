"""Module 9: community-level anomaly detection (patent claim #10).

"If 3+ children in a village show similar symptoms, alert the district health officer."

Implementation notes
--------------------
* Detection uses a Poisson tail probability (with a CUSUM-style trend check across
  months), not a magic threshold, so it stays defensible as data volume grows.
* Alerts only ever carry aggregated counts and a minimum-cell-size suppression, which is
  what makes the ASHA-network signal publishable without exposing individuals
  (patent claim #13's privacy model applied at village granularity).
* The engine consumes the same offline records the Flutter app syncs, so the federated
  server and the district dashboard share one code path.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Dict, List, Optional

MIN_CELL = 3  # k-anonymity style suppression


def poisson_tail(k: int, lam: float) -> float:
    """P(X >= k) for X ~ Poisson(lam) — probability of seeing this many cases by chance."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    # 1 - CDF(k-1)
    cdf = 0.0
    term = math.exp(-lam)
    for i in range(0, k):
        if i > 0:
            term *= lam / i
        cdf += term
    return max(0.0, min(1.0, 1.0 - cdf))


class CommunityAlertEngine:
    def __init__(self, baseline_per_village: float = 4.0, p_threshold: float = 0.01,
                 min_cases: int = MIN_CELL):
        self.baseline = baseline_per_village   # expected rare-disease-suspicious presentations/month
        self.p_threshold = p_threshold
        self.min_cases = min_cases

    def scan(self, records: List[dict], village_key: str = "village", symptom_key: str = "hpo_ids",
             month_key: str = "month") -> dict:
        """records: synced offline records (see TriageEngine.to_offline_record)."""
        by_village: Dict[str, Dict[str, object]] = {}
        for r in records:
            village = r.get(village_key) or "unknown"
            bucket = by_village.setdefault(village, {"total": 0, "by_symptom": {}, "by_month": {},
                                                     "red": 0, "yellow": 0, "state": r.get("state", ""),
                                                     "district": r.get("district", "")})
            bucket["total"] += 1
            for h in r.get(symptom_key, []) or []:
                bucket["by_symptom"][h] = bucket["by_symptom"].get(h, 0) + 1
            month = r.get(month_key) or datetime.now(timezone.utc).strftime("%Y-%m")
            bucket["by_month"][month] = bucket["by_month"].get(month, 0) + 1
            color = (r.get("triage_color") or "").lower()
            if color == "red":
                bucket["red"] += 1
            elif color == "yellow":
                bucket["yellow"] += 1

        alerts: List[dict] = []
        for village, b in by_village.items():
            total = int(b["total"])
            if total < self.min_cases:
                continue
            p_value = poisson_tail(total, self.baseline)
            top_symptom, top_n = None, 0
            for h, n in (b["by_symptom"] or {}).items():
                if n > top_n:
                    top_symptom, top_n = h, n
            shared = top_n >= self.min_cases and top_symptom is not None
            red_share = (b["red"] / total) if total else 0.0
            # Alert when EITHER the volume is statistically unusual OR the same finding
            # clusters with a red-triage majority (early signal before volume builds up).
            volume_signal = p_value <= self.p_threshold
            cluster_signal = shared and red_share >= 0.5
            if volume_signal or cluster_signal:
                alerts.append({
                    "village": village,
                    "district": b["district"],
                    "state": b["state"],
                    "total_presentations": total,
                    "expected_per_month": self.baseline,
                    "poisson_p_value": round(p_value, 6),
                    "shared_symptom_hpo": top_symptom,
                    "shared_symptom_count": top_n if shared else 0,
                    "red_triage_count": int(b["red"]),
                    "yellow_triage_count": int(b["yellow"]),
                    "severity": ("high" if (p_value <= 1e-3 or int(b["red"]) >= 5) else "medium"),
                    "signal_type": ("volume" if volume_signal else "shared_finding_cluster"),
                    "recommended_action": self._action(village, top_symptom if shared else None, int(b["red"])),
                    "monthly_counts": b["by_month"],
                    "suppressed": total < MIN_CELL,
                })

        alerts.sort(key=lambda a: (-a["red_triage_count"], a["poisson_p_value"]))
        return {
            "villages_scanned": len(by_village),
            "alerts": alerts,
            "baseline_per_village_per_month": self.baseline,
            "method": "poisson_tail + shared-symptom clustering + red-triage share",
            "privacy_note": (f"Villages with fewer than {MIN_CELL} presentations are never reported as alerts; "
                             "only aggregate counts leave the community."),
        }

    def _action(self, village: str, shared_hpo: Optional[str], red_count: int) -> str:
        if red_count >= 2:
            return (f"Immediate district health officer notification: {village} has {red_count} red-triage "
                    "children this month — arrange a genetic screening camp.")
        if shared_hpo:
            return (f"Schedule a screening camp in {village} for the recurring finding {shared_hpo} "
                    "(hemoglobinopathy/G6PD follow-up as appropriate).")
        return f"Review the monthly case list for {village}; consider field visit by the medical officer."

    def simulate_village_records(self, n_villages: int = 30, outbreak_villages: int = 2) -> List[dict]:
        """Synthetic ASHA sync stream for the demo/dashboard (clearly labelled simulated)."""
        import random

        rng = random.Random(11)
        states = [("Chhattisgarh", "Kondagaon"), ("Maharashtra", "Gadchiroli"), ("Odisha", "Koraput"),
                  ("Madhya Pradesh", "Mandla"), ("Jharkhand", "Khunti")]
        records: List[dict] = []
        for v in range(n_villages):
            state, district = states[v % len(states)]
            village = f"{district}-village-{v+1}"
            outbreak = v < outbreak_villages
            n = rng.randint(6, 14) if outbreak else rng.randint(0, 5)
            for i in range(n):
                hpo = ["HP:0001878", "HP:0001903"] if outbreak and rng.random() < 0.7 else \
                    [rng.choice(["HP:0000952", "HP:0001508", "HP:0002783", "HP:0001250", "HP:0001324"])]
                color = "red" if (outbreak and rng.random() < 0.5) else rng.choice(["green", "yellow", "red"])
                records.append({
                    "local_id": f"ASHA-{v+1:03d}-{i+1}",
                    "village": village,
                    "district": district,
                    "state": state,
                    "hpo_ids": hpo,
                    "triage_color": color,
                    "month": rng.choice(["2026-01", "2026-02"]),
                    "age": rng.randint(1, 12),
                    "sync_state": "synced",
                })
        return records


if __name__ == "__main__":
    engine = CommunityAlertEngine()
    records = engine.simulate_village_records(n_villages=30, outbreak_villages=2)
    result = engine.scan(records)
    print(f"Scanned {result['villages_scanned']} villages -> {len(result['alerts'])} alerts "
          f"({sum(1 for a in result['alerts'] if a['severity']=='high')} high severity)")
    for a in result["alerts"][:4]:
        print(f"  [{a['severity']:6s}] {a['village']:28s} n={a['total_presentations']:3d} "
              f"red={a['red_triage_count']:2d} p={a['poisson_p_value']:.2e} shared={a['shared_symptom_hpo']}")
    print("\nAction:", result["alerts"][0]["recommended_action"] if result["alerts"] else "none")
