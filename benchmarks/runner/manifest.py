"""Benchmark manifests: discover instances and their expected results."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "benchmarks"


@dataclass(frozen=True)
class Instance:
    path: Path
    expected: str  # "sat" | "unsat" | "unknown"
    family: str
    tags: tuple[str, ...] = ()


def _expected_from_name(p: Path) -> str:
    name = p.name.lower()
    if "unsat" in name:
        return "unsat"
    if "sat" in name:
        return "sat"
    return "unknown"


def load_family(family: str) -> list[Instance]:
    """Load instances for a family path relative to benchmarks/.

    If a `manifest.json` exists in the family directory it is
    authoritative; otherwise glob `*.dqdimacs[.gz]` and infer expected
    results from filenames.
    """
    base = BENCH / family
    mf = base / "manifest.json"
    if mf.exists():
        raw = json.loads(mf.read_text())
        return [
            Instance(
                path=base / e["path"],
                expected=e.get("expected", "unknown"),
                family=family,
                tags=tuple(e.get("tags", ())),
            )
            for e in raw
        ]
    out: list[Instance] = []
    for pat in ("*.dqdimacs", "*.dqdimacs.gz"):
        for p in sorted(base.rglob(pat)):
            out.append(Instance(path=p, expected=_expected_from_name(p), family=family))
    return out
