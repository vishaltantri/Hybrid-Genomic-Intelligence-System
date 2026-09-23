"""Concept drift detection for rare-disease pattern shifts (Module 10, patent claim #12).

Three monitors:
  * Population Stability Index (PSI) over categorical distributions — disease mix,
    language mix, triage colour mix.
  * Kolmogorov-Smirnov statistic over numeric streams — symptom counts per case,
    diagnosis delay, model confidence.
  * Rolling uncertainty monitor — if the model's own confidence distribution drifts down,
    flag it even when inputs look stable (silent degradation).

Thresholds follow standard industry practice (PSI < 0.1 stable, 0.1-0.25 moderate,
> 0.25 significant shift).
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence

import numpy as np

HIGH_CONFIDENCE = 1 - 1e-6


def psi(expected: Sequence[float], actual: Sequence[float], buckets: int = 10, eps: float = 1e-6) -> float:
    """Population Stability Index between two numeric samples."""
    expected, actual = np.asarray(expected, dtype="float64"), np.asarray(actual, dtype="float64")
    if expected.size == 0 or actual.size == 0:
        return 0.0
    lo, hi = min(expected.min(), actual.min()), max(expected.max(), actual.max())
    if hi <= lo:
        return 0.0
    edges = np.linspace(lo, hi, buckets + 1)
    e_hist, _ = np.histogram(expected, bins=edges)
    a_hist, _ = np.histogram(actual, bins=edges)
    e_pct = np.clip(e_hist / max(e_hist.sum(), 1), eps, None)
    a_pct = np.clip(a_hist / max(a_hist.sum(), 1), eps, None)
    return float(np.sum((a_pct - e_pct) * np.log(a_pct / e_pct)))


def psi_categorical(expected_counts: Dict[str, int], actual_counts: Dict[str, int], eps: float = 1e-6) -> float:
    keys = sorted(set(expected_counts) | set(actual_counts))
    e_total = sum(expected_counts.values()) or 1
    a_total = sum(actual_counts.values()) or 1
    total = 0.0
    for k in keys:
        e = max(expected_counts.get(k, 0) / e_total, eps)
        a = max(actual_counts.get(k, 0) / a_total, eps)
        total += (a - e) * math.log(a / e)
    return float(total)


def ks_statistic(expected: Sequence[float], actual: Sequence[float]) -> Dict[str, float]:
    """Two-sample Kolmogorov-Smirnov statistic with an asymptotic p-value."""
    e = np.sort(np.asarray(expected, dtype="float64"))
    a = np.sort(np.asarray(actual, dtype="float64"))
    if e.size == 0 or a.size == 0:
        return {"statistic": 0.0, "p_value": 1.0, "n_expected": int(e.size), "n_actual": int(a.size)}
    combined = np.concatenate([e, a])
    cdf_e = np.searchsorted(e, combined, side="right") / e.size
    cdf_a = np.searchsorted(a, combined, side="right") / a.size
    d = float(np.max(np.abs(cdf_e - cdf_a)))
    if d == 0.0:
        # Identical samples: no evidence of any distribution shift.
        return {"statistic": 0.0, "p_value": 1.0, "n_expected": int(e.size), "n_actual": int(a.size)}
    en = math.sqrt(e.size * a.size / (e.size + a.size))
    lam = (en + 0.12 + 0.11 / en) * d
    p = 2 * sum((-1) ** (k - 1) * math.exp(-2 * k * k * lam * lam) for k in range(1, 101))
    return {"statistic": round(d, 4), "p_value": round(max(0.0, min(1.0, p)), 6),
            "n_expected": int(e.size), "n_actual": int(a.size)}


def classify_psi(value: float) -> str:
    if value < 0.1:
        return "stable"
    if value < 0.25:
        return "moderate_shift"
    return "significant_shift"


class DriftMonitor:
    def __init__(self, reference: Dict[str, List[float]] | None = None):
        self.reference = reference or {}

    def set_reference(self, name: str, values: Sequence[float]) -> None:
        self.reference[name] = list(values)

    def check_numeric(self, name: str, current: Sequence[float]) -> Dict:
        if name not in self.reference:
            return {"metric": name, "status": "no_reference"}
        value = psi(self.reference[name], current)
        ks = ks_statistic(self.reference[name], current)
        status = classify_psi(value)
        if status == "significant_shift" or ks["p_value"] < 0.01:
            status = "significant_shift"
        return {"metric": name, "psi": round(value, 4), "status": status, "ks": ks,
                "action": self._action(status, name)}

    def check_categorical(self, name: str, reference_counts: Dict[str, int], current_counts: Dict[str, int]) -> Dict:
        value = psi_categorical(reference_counts, current_counts)
        status = classify_psi(value)
        return {"metric": name, "psi": round(value, 4), "status": status,
                "reference_distribution": reference_counts, "current_distribution": current_counts,
                "action": self._action(status, name)}

    def check_confidences(self, reference_conf: Sequence[float], current_conf: Sequence[float]) -> Dict:
        r = float(np.mean(reference_conf)) if len(reference_conf) else 0.0
        c = float(np.mean(current_conf)) if len(current_conf) else 0.0
        drop = r - c
        status = "significant_shift" if drop >= 0.10 else ("moderate_shift" if drop >= 0.05 else "stable")
        return {"metric": "model_confidence", "reference_mean": round(r, 4), "current_mean": round(c, 4),
                "drop": round(drop, 4), "status": status,
                "note": "Confidence decay can indicate drift even when input distributions look stable.",
                "action": self._action(status, "model_confidence")}

    def _action(self, status: str, metric: str) -> str:
        if status == "significant_shift":
            return f"Trigger retraining review for {metric}; check for new variant/disease reporting patterns."
        if status == "moderate_shift":
            return f"Monitor {metric} weekly and expand active-learning sampling."
        return "No action."

    def report(self, streams: Dict[str, Sequence[float]]) -> Dict:
        checks = [self.check_numeric(name, values) for name, values in streams.items()]
        worst = "stable"
        for c in checks:
            if c.get("status") == "significant_shift":
                worst = "significant_shift"
                break
            if c.get("status") == "moderate_shift":
                worst = "moderate_shift"
        return {"checks": checks, "overall_status": worst,
                "retraining_needed": worst == "significant_shift"}


def simulate_drift_example(seed: int = 3) -> Dict:
    """Demonstrate the monitor on synthetic 'post-outbreak referral pattern' data."""
    rng = np.random.default_rng(seed)
    ref_conf = rng.normal(0.82, 0.05, 400).clip(0, 1)
    cur_conf = rng.normal(0.70, 0.06, 400).clip(0, 1)
    ref_symptoms = rng.poisson(3.0, 400)
    cur_symptoms = rng.poisson(4.6, 400)
    ref_mix = {"ORPHA:231222": 40, "ORPHA:232": 30, "ORPHA:915": 10, "ORPHA:98863": 20}
    cur_mix = {"ORPHA:231222": 22, "ORPHA:232": 70, "ORPHA:915": 6, "ORPHA:98863": 12}
    monitor = DriftMonitor()
    monitor.set_reference("symptoms_per_case", ref_symptoms)
    monitor.set_reference("model_confidence", ref_conf)
    report = monitor.report({"symptoms_per_case": cur_symptoms, "model_confidence": cur_conf})
    report["checks"].append(monitor.check_categorical("disease_mix", ref_mix, cur_mix))
    return report


if __name__ == "__main__":
    report = simulate_drift_example()
    print(f"Overall: {report['overall_status']} | retraining needed: {report['retraining_needed']}")
    for c in report["checks"]:
        if c.get("metric") == "disease_mix":
            print(f"  {c['metric']:20s} psi={c['psi']:.3f} {c['status']}")
        elif "psi" in c:
            print(f"  {c['metric']:20s} psi={c['psi']:.3f} ks_p={c['ks']['p_value']:.4f} {c['status']}")
        else:
            print(f"  {c['metric']:20s} drop={c['drop']:.3f} {c['status']}")
    print("Action:", report["checks"][0]["action"])
