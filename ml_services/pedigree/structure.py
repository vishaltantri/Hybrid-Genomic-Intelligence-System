"""Pedigree structure: derived relationships, generations, consanguinity and validation (Phase 3E).

Only two canonical edge types are stored: ``parent_of`` (member_a is a biological parent of member_b) and
``partner`` (symmetric). Child, sibling, half-sibling, grandparent, aunt/uncle, niece/nephew, cousin, ... are
*derived* here, so a relationship can never be recorded one-way or contradict another.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

PARENT_OF = "parent_of"
PARTNER = "partner"
SEXES = ("M", "F", "U")
AFFECTED_STATES = ("affected", "unaffected", "unknown")
MIN_PARENT_AGE_GAP = 12  # years; smaller gaps are flagged as implausible (warning), negative gaps as errors


class Graph:
    """Adjacency view over members and canonical relationships."""

    def __init__(self, members: List[dict], rels: List[dict]):
        self.members = {m["member_id"]: m for m in members}
        self.rels = rels
        self.parents: Dict[str, List[str]] = defaultdict(list)
        self.children: Dict[str, List[str]] = defaultdict(list)
        self.partners: Dict[str, Set[str]] = defaultdict(set)
        for r in rels:
            a, b = r["member_a"], r["member_b"]
            if a not in self.members or b not in self.members:
                continue
            if r["rel_type"] == PARENT_OF:
                if a not in self.parents[b]:
                    self.parents[b].append(a)
                if b not in self.children[a]:
                    self.children[a].append(b)
            elif r["rel_type"] == PARTNER:
                self.partners[a].add(b)
                self.partners[b].add(a)

    def ancestors(self, mid: str, limit: int = 12) -> Dict[str, int]:
        """ancestor id -> number of generations above `mid` (shortest path)."""
        out: Dict[str, int] = {}
        frontier = [(p, 1) for p in self.parents.get(mid, [])]
        while frontier and limit:
            nxt = []
            for pid, d in frontier:
                if pid not in out or d < out[pid]:
                    out[pid] = d
                    nxt += [(pp, d + 1) for pp in self.parents.get(pid, [])]
            frontier, limit = nxt, limit - 1
        return out

    def descendants(self, mid: str) -> Set[str]:
        seen: Set[str] = set()
        stack = list(self.children.get(mid, []))
        while stack:
            c = stack.pop()
            if c not in seen:
                seen.add(c)
                stack += self.children.get(c, [])
        return seen

    def father(self, mid: str) -> Optional[dict]:
        for p in self.parents.get(mid, []):
            if self.members[p]["sex"] == "M":
                return self.members[p]
        return None

    def mother(self, mid: str) -> Optional[dict]:
        for p in self.parents.get(mid, []):
            if self.members[p]["sex"] == "F":
                return self.members[p]
        return None


def creates_cycle(g: Graph, parent: str, child: str) -> bool:
    """Would `parent` become an ancestor of itself if `parent` is made a parent of `child`?"""
    return parent == child or parent in g.descendants(child)


# ------------------------------- generations -------------------------------

def compute_generations(g: Graph) -> Tuple[Dict[str, int], Dict[str, int]]:
    """(aligned generations, raw generations). Raw = from ancestry only; aligned also puts partners on one row."""
    raw: Dict[str, int] = {}

    def depth(mid: str, stack: Tuple[str, ...] = ()) -> int:
        if mid in raw:
            return raw[mid]
        if mid in stack:
            return 0  # cycle: validation reports it
        ps = g.parents.get(mid, [])
        raw[mid] = 0 if not ps else 1 + max(depth(p, stack + (mid,)) for p in ps)
        return raw[mid]

    for mid in g.members:
        depth(mid)
    aligned = dict(raw)
    for _ in range(len(g.members) + 1):
        changed = False
        for a, ps in g.partners.items():
            for b in ps:
                top = max(aligned[a], aligned[b])
                if aligned[a] != top or aligned[b] != top:
                    aligned[a] = aligned[b] = top
                    changed = True
        # push descendants below their (possibly raised) parents
        for child, ps in g.parents.items():
            need = 1 + max(aligned[p] for p in ps)
            if aligned[child] < need:
                aligned[child] = need
                changed = True
        if not changed:
            break
    return aligned, raw


# ------------------------------- derived relationships -------------------------------

def _sx(m: dict, male: str, female: str, neutral: str) -> str:
    return {"M": male, "F": female}.get(m["sex"], neutral)


def derive_relations(g: Graph, ref_id: str) -> Dict[str, str]:
    """Label every member relative to `ref_id` (normally the proband)."""
    out: Dict[str, str] = {}
    if ref_id not in g.members:
        return out
    ref_parents = set(g.parents.get(ref_id, []))
    anc = g.ancestors(ref_id)
    for mid, m in g.members.items():
        if mid == ref_id:
            out[mid] = "self"
        elif mid in ref_parents:
            out[mid] = _sx(m, "father", "mother", "parent")
        elif mid in g.children.get(ref_id, []):
            out[mid] = _sx(m, "son", "daughter", "child")
        elif mid in g.partners.get(ref_id, set()):
            out[mid] = "partner"
        elif anc.get(mid) == 2:
            out[mid] = _sx(m, "grandfather", "grandmother", "grandparent")
        elif mid in anc:
            out[mid] = f"ancestor ({anc[mid]} generations up)"
        else:
            their_parents = set(g.parents.get(mid, []))
            shared = their_parents & ref_parents
            if shared and ref_parents:
                full = len(shared) >= 2 or (their_parents == ref_parents and len(ref_parents) >= 2)
                out[mid] = _sx(m, "brother", "sister", "sibling") if full else _sx(m, "half-brother", "half-sister", "half-sibling")
                continue
            desc = g.descendants(ref_id)
            if mid in desc:
                depth = 0
                frontier, seen = set(g.children[ref_id]), set()
                while frontier:
                    depth += 1
                    if mid in frontier:
                        break
                    seen |= frontier
                    frontier = {c for f in frontier for c in g.children.get(f, [])} - seen
                out[mid] = "grandchild" if depth == 2 else f"descendant ({depth} generations down)"
                continue
            # aunt/uncle: sibling of a parent;  niece/nephew: child of a sibling;  cousin: child of aunt/uncle
            label = None
            for p in ref_parents:
                if g.parents.get(mid) and set(g.parents[mid]) & set(g.parents.get(p, [])) and mid != p:
                    label = _sx(m, "uncle", "aunt", "aunt/uncle")
            if label is None:
                for sib in [s for s, lbl in out.items() if "brother" in lbl or "sister" in lbl or "sibling" in lbl]:
                    if sib in g.parents.get(mid, []):
                        label = _sx(m, "nephew", "niece", "niece/nephew")
            if label is None:
                for p in ref_parents:
                    for au in g.members:
                        if au != p and set(g.parents.get(au, [])) & set(g.parents.get(p, [])) and au in g.parents.get(mid, []):
                            label = "cousin"
            out[mid] = label or ("in-law / partner's relative" if any(pp in g.partners.get(mid, set()) or mid in g.partners.get(pp, set()) for pp in g.members) else "other relative")
    return out


def consanguinity_key(g: Graph, a: str, b: str) -> Optional[str]:
    """Relationship key understood by the reproductive module (first_cousins / uncle_niece / ...), from the pedigree."""
    aa, ab = g.ancestors(a), g.ancestors(b)
    best = None
    for anc in set(aa) & set(ab):
        pair = (aa[anc], ab[anc])
        best = pair if best is None or sum(pair) < sum(best) else best
    if best is None:
        return None
    if best == (1, 1):
        return "siblings"
    if sorted(best) == [1, 2]:
        return "uncle_niece"
    if best == (2, 2):
        return "first_cousins"
    if best == (3, 3):
        return "second_cousins"
    return None


# ------------------------------- validation -------------------------------

def validate(members: List[dict], rels: List[dict]) -> List[dict]:
    issues: List[dict] = []

    def add(sev: str, code: str, msg: str, ids: Optional[List[str]] = None):
        issues.append({"severity": sev, "code": code, "message": msg, "members": ids or []})

    ids = {m["member_id"] for m in members}
    label = {m["member_id"]: m["label"] for m in members}
    seen: Set[Tuple[str, str, str]] = set()
    clean: List[dict] = []
    for r in rels:
        a, b, t = r["member_a"], r["member_b"], r["rel_type"]
        if a == b:
            add("error", "SELF_RELATION", f"{label.get(a, a)} is connected to themselves.", [a])
            continue
        if a not in ids or b not in ids:
            add("error", "UNKNOWN_MEMBER", f"Relationship {r.get('rel_id', '')} refers to a member that does not exist.")
            continue
        key = (t, a, b) if t == PARENT_OF else (t,) + tuple(sorted((a, b)))
        if key in seen:
            add("error", "DUPLICATE_RELATIONSHIP", f"Duplicate {t.replace('_', ' ')} relationship between {label[a]} and {label[b]}.", [a, b])
            continue
        seen.add(key)
        clean.append(r)
    g = Graph(members, clean)

    for mid in g.members:
        if mid in g.descendants(mid):
            add("error", "ANCESTOR_CYCLE", f"{label[mid]} is recorded as their own ancestor (impossible parent-child loop).", [mid])
    for a, ps in g.partners.items():
        for b in ps:
            if a < b and (b in g.parents.get(a, []) or a in g.parents.get(b, [])):
                add("error", "PARTNER_IS_PARENT", f"{label[a]} and {label[b]} are recorded as both partners and parent/child.", [a, b])
            if a < b and b in g.descendants(a) | set(g.ancestors(a)) and not (b in g.parents.get(a, []) or a in g.parents.get(b, [])):
                add("error", "PARTNER_IS_LINEAL_RELATIVE", f"{label[a]} and {label[b]} are partners but also lineal relatives.", [a, b])
            if a < b:
                key = consanguinity_key(g, a, b)
                if key:
                    add("info", "CONSANGUINEOUS_PARTNERS", f"{label[a]} and {label[b]} are partners and related ({key.replace('_', ' ')}).", [a, b])

    for child, ps in g.parents.items():
        if len(ps) > 2:
            add("error", "TOO_MANY_PARENTS", f"{label[child]} has {len(ps)} biological parents recorded (maximum 2).", [child] + ps)
        sexes = [g.members[p]["sex"] for p in ps]
        if len(ps) == 2 and sexes[0] == sexes[1] and sexes[0] in ("M", "F"):
            add("warning", "SAME_SEX_PARENTS", f"Both biological parents of {label[child]} are recorded as {'male' if sexes[0] == 'M' else 'female'}; "
                                              "biological parentage requires one male and one female parent.", [child] + ps)
        cage = g.members[child].get("age_years")
        for p in ps:
            page = g.members[p].get("age_years")
            if page is not None and cage is not None:
                if page <= cage:
                    add("error", "PARENT_NOT_OLDER", f"{label[p]} ({page}y) is recorded as a parent of {label[child]} ({cage}y) but is not older.", [p, child])
                elif page - cage < MIN_PARENT_AGE_GAP:
                    add("warning", "IMPLAUSIBLE_AGE_GAP", f"{label[p]} is only {page - cage} years older than their child {label[child]}.", [p, child])
        if len(ps) == 1:
            add("info", "MISSING_PARENT", f"Only one parent of {label[child]} is recorded.", [child])

    aligned, raw = compute_generations(g)
    for a, ps in g.partners.items():
        for b in ps:
            if a < b and raw.get(a) != raw.get(b) and not (b in g.descendants(a) or a in g.descendants(b)):
                add("info", "PARTNER_GENERATION_MISMATCH",
                    f"{label[a]} and {label[b]} are partners but only one of them has recorded parents; they are drawn on the same row "
                    "(the other partner is treated as marrying in).", [a, b])

    probands = [m["member_id"] for m in members if m.get("is_proband")]
    if len(probands) > 1:
        add("error", "MULTIPLE_PROBANDS", "More than one proband is marked; a case has a single primary proband.", probands)
    if members and not probands:
        add("warning", "NO_PROBAND", "No proband is designated for this pedigree.")
    for m in members:
        if m.get("is_proband") and m.get("affected") == "unaffected":
            add("warning", "UNAFFECTED_PROBAND", f"{m['label']} is the proband but is marked unaffected.", [m["member_id"]])
    if members and not any(r["rel_type"] == PARENT_OF for r in clean) and len(members) > 1:
        add("info", "NO_PARENT_LINKS", "No parent-child relationships are recorded yet; inheritance analysis needs them.")
    return issues
