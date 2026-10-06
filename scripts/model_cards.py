"""Generate docs/model_cards/*.md from models/registry.json (run after `python -m scripts.ml_benchmark`). Content is the registry's
measured values and notes only; nothing is added by hand."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    reg = json.loads((ROOT / "models" / "registry.json").read_text(encoding="utf-8"))
    out = ROOT / "docs" / "model_cards"
    out.mkdir(parents=True, exist_ok=True)
    for m in reg["models"]:
        met = m.get("metrics")
        body = json.dumps(met, indent=2) if isinstance(met, (dict, list)) else str(met or "Not evaluated - ground truth unavailable")
        (out / f"{m['id']}.md").write_text(
            f"""# Model card: {m['id']}

- Version: {m.get('version', 'n/a')}
- Status: {m['status']}
- On by default: {m['default_on']}
- Reproducible across two runs: {m.get('reproducible', m.get('deterministic', 'not checked'))}
- Intended use: decision support for clinicians; not a diagnostic device.

## Measured metrics (generated {reg['generated_utc']})

```
{body}
```

## Limitations

{m.get('note', 'See docs/ML_BENCHMARK.md: synthetic cases are circular and no real outcome data exists.')}
""", encoding="utf-8")
    print(f"wrote {len(reg['models'])} cards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
