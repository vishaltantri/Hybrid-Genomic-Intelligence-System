"""Pedigree diagram generator (Module 6: "auto-generates family pedigree diagrams").

Emits Mermaid graph text (renders in the React dashboard / docs) and a compact ASCII
fallback for terminals and PDF text exports. No external dependency.
"""
from __future__ import annotations

from typing import Dict, List, Optional

# Mermaid node shapes: square = male, circle = female, filled = affected
SYMBOL = {"male": "[ ]", "female": "( )", "affected_male": "[X]", "affected_female": "(X)",
          "carrier": "(C)", "unknown": "[?]"}


def build_pedigree(family: Dict, disease_name: str = "", consanguineous: bool = False) -> dict:
    """family = {"grandparents": [...], "parents": [...], "children": [...], "siblings": [...]}

    Each person: {"id": "P1", "name": "Father", "sex": "M", "affected": bool, "carrier": bool}
    """
    people: List[dict] = []
    for group in ("grandparents", "parents", "children", "siblings"):
        for person in family.get(group, []) or []:
            p = dict(person)
            p["group"] = group
            people.append(p)

    lines = ["graph TD"]
    lines.append(f'  title["Pedigree — {disease_name or "family"}"]')
    for p in people:
        sex = (p.get("sex") or "U").upper()
        if p.get("affected"):
            shape = "[X]" if sex.startswith("M") else "(X)" if sex.startswith("F") else "[X]"
        elif p.get("carrier"):
            shape = "(C)" if sex.startswith("F") else "[C]"
        else:
            shape = "[ ]" if sex.startswith("M") else "( )" if sex.startswith("F") else "[?]"
        label = f'{p.get("name") or p["id"]} {shape}'
        lines.append(f'  {p["id"]}["{label}"]')

    parents = [p for p in people if p["group"] == "parents"]
    if len(parents) >= 2:
        a, b = parents[0], parents[1]
        link = "x---x" if consanguineous else "---"
        lines.append(f'  {a["id"]} {link} {b["id"]}')
    children = [p for p in people if p["group"] in ("children", "siblings")]
    if parents and children:
        for c in children:
            lines.append(f'  {parents[0]["id"]} --> {c["id"]}')
    for gp in [p for p in people if p["group"] == "grandparents"]:
        same_family = [x for x in people if x["group"] == "parents" and (x.get("parent_id") == gp["id"])]
        for x in same_family:
            lines.append(f'  {gp["id"]} --> {x["id"]}')

    mermaid = "\n".join(lines)
    ascii_art = _ascii_pedigree(parents, children, consanguineous)
    legend = ("[ ] male  ( ) female  [X]/(X) affected  [C]/(C) carrier  "
              + ("=== consanguineous union" if consanguineous else "--- unrelated union"))
    return {"mermaid": mermaid, "ascii": ascii_art, "legend": legend,
            "n_people": len(people), "consanguineous": consanguineous}


def _ascii_pedigree(parents: List[dict], children: List[dict], consanguineous: bool) -> str:
    def sym(p: dict) -> str:
        sex = (p.get("sex") or "U").upper()
        if p.get("affected"):
            return "X"
        if p.get("carrier"):
            return "C"
        return "M" if sex.startswith("M") else "F" if sex.startswith("F") else "?"

    if len(parents) >= 2:
        union = "===" if consanguineous else "---"
        top = f"  {parents[0].get('name', parents[0]['id'])}[{sym(parents[0])}] {union} " \
              f"{parents[1].get('name', parents[1]['id'])}[{sym(parents[1])}]"
    elif parents:
        top = f"  {parents[0].get('name', parents[0]['id'])}[{sym(parents[0])}]"
    else:
        top = "  (no parents recorded)"
    if children:
        mid = "   |"
        kids = "  " + "   ".join(f"{c.get('name', c['id'])}[{sym(c)}]" for c in children)
    else:
        mid, kids = "", "  (no children recorded)"
    return "\n".join([top, mid, kids]).strip("\n")


def from_seed_case(case: dict, disease_name: str = "") -> dict:
    """Convenience: build a two-parent + one-child pedigree sketch from a case record."""
    family = {
        "parents": [
            {"id": "P1", "name": "Father", "sex": (case.get("sex") or "M").replace("F", "M"), "carrier": False},
            {"id": "P2", "name": "Mother", "sex": "F", "carrier": False},
        ],
        "children": [
            {"id": "C1", "name": "Patient", "sex": case.get("sex", "M"), "affected": True},
        ],
    }
    return build_pedigree(family, disease_name, consanguineous=bool(case.get("consanguinity")))


if __name__ == "__main__":
    fam = {
        "grandparents": [{"id": "G1", "name": "Grandfather", "sex": "M"}, {"id": "G2", "name": "Grandmother", "sex": "F"}],
        "parents": [{"id": "P1", "name": "Father", "sex": "M"}, {"id": "P2", "name": "Mother", "sex": "F", "carrier": True}],
        "children": [{"id": "C1", "name": "Patient", "sex": "M", "affected": True},
                     {"id": "C2", "name": "Sister", "sex": "F"}],
    }
    ped = build_pedigree(fam, "Beta-thalassemia", consanguineous=False)
    print(ped["ascii"])
    print("\n" + ped["legend"])
    print("\nMermaid (first lines):")
    print("\n".join(ped["mermaid"].splitlines()[:6]))
