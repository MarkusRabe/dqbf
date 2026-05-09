"""Audit benchmark families: which are mathematically QBF (linear
prefix) and which are HWMC (derived from a sequential .aag)?

A DQBF prefix is *linear* (i.e. expressible in QDIMACS `e`/`a` lines)
iff the dependency sets are nested: for any two existentials y, z,
either dep(y) ⊆ dep(z) or dep(z) ⊆ dep(y). Then sort by |dep| to get
the alternation order. We additionally check that the resulting prefix
has at most a few alternations (most are 2QBF or 3QBF).

Run: `python -m scripts.audit_domains`
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from core.dqdimacs import load


def is_linear(f) -> tuple[bool, int]:
    """Return (is_linear, n_alternations). n_alternations counts how
    many distinct dep-set sizes appear in the existential block (1 = no
    inner ∀, i.e. this is 2QBF: ∀U ∃E)."""
    deps = [frozenset(f.dep(e)) for e in f.existentials]
    if not deps:
        return True, 0
    deps_sorted = sorted(set(deps), key=len)
    for i in range(len(deps_sorted) - 1):
        if not deps_sorted[i] <= deps_sorted[i + 1]:
            return False, 0
    return True, len(deps_sorted)


def find_aag(variant_dir: Path, root: Path) -> bool:
    """Does this variant (or any sibling variant in the same family)
    have committed .aag sources? Mirrors `_find_source_aag`'s sibling
    search."""
    fam = variant_dir
    while fam.parent != root and fam.parent.name != "train":
        fam = fam.parent
    return any(fam.rglob("*.aag"))


def manifest_says_no_source(variant_dir: Path) -> bool:
    """True if every manifest entry has source_aag=None (PEC families)."""
    mf = variant_dir / "manifest.json"
    if not mf.exists():
        return False
    try:
        entries = json.loads(mf.read_text())
        if isinstance(entries, dict):
            entries = entries.get("instances", [])
        return bool(entries) and all(
            "source_aag" in e and e["source_aag"] is None for e in entries
        )
    except Exception:
        return False


def audit() -> list[dict]:
    root = Path("benchmarks/train")
    out: list[dict] = []
    for mf in sorted(root.rglob("manifest.json")):
        variant_dir = mf.parent
        try:
            entries = json.loads(mf.read_text())
            if isinstance(entries, dict):
                entries = entries.get("instances", [])
        except Exception:
            continue
        if not entries:
            continue
        fam = str(variant_dir.relative_to(root))
        # Sample the first 3 instances and check linearity.
        linear, alts, n_checked = True, 0, 0
        for e in entries[:3]:
            rel = e.get("path") or e.get("name") or e.get("file")
            if rel is None:
                continue
            p = variant_dir / rel
            if not p.exists():
                continue
            f = load(str(p))
            lin, a = is_linear(f)
            linear = linear and lin
            alts = max(alts, a)
            n_checked += 1
        if n_checked == 0:
            continue
        has_aag = find_aag(variant_dir, root)
        no_source = manifest_says_no_source(variant_dir)
        is_hwmc = has_aag and not no_source
        domains = ["dqbf"]
        if linear:
            domains.append("qbf")
        if is_hwmc:
            domains.append("hwmc")
        if "syntcomp" in fam or any(variant_dir.rglob("*.tlsf")):
            domains.append("syntcomp")
        out.append(
            {
                "family": fam,
                "linear": linear,
                "alts": alts,
                "has_aag": has_aag,
                "no_source": no_source,
                "domains": domains,
                "n_inst": len(entries),
            }
        )
    return out


def main() -> int:
    rows = audit()
    print(f"{'family':<42}{'linear':>7}{'alts':>5}{'.aag':>6}{'domains'}")
    print("-" * 90)
    for r in rows:
        print(
            f"{r['family']:<42}{str(r['linear']):>7}{r['alts']:>5}"
            f"{('yes' if r['has_aag'] else '—'):>6}  {','.join(r['domains'])}"
        )
    by_dom: dict[str, int] = {}
    for r in rows:
        for d in r["domains"]:
            by_dom[d] = by_dom.get(d, 0) + 1
    print("-" * 90)
    print("families per domain:", by_dom)
    return 0


if __name__ == "__main__":
    sys.exit(main())
