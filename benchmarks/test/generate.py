"""Generate manifests for the test-set benchmarks.

The test set holds external/competition instances (DQBF QBFLIB,
HWMCC, SYNTCOMP). Unlike `train/`, the instances are not generated
here — they're committed verbatim. This script just writes
`manifest.json` files in the train-set convention so the runner and
report discover them properly.

`expected` is derived from filename hints (`*-sat`/`*-unsat`/`*_sat`)
where present; otherwise `unknown`. **Never set `expected` from a
solver probe** — only from the upstream source's labelling.

Layout (mirrors `train/<family>/<variant>/`):
    test/dqbf_qbflib/{balabanov,bloem,scholl}/
        manifest.json
        *.dqdimacs.gz
    test/hwmcc/...   (when populated)
    test/syntcomp/...

Usage:
    python -m benchmarks.test.generate [--dry-run]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Filename → expected verdict, matched in order. Conservative: only
# recognise unambiguous suffix conventions.
_EXPECTED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[-_]unsat\b", re.I), "unsat"),
    (re.compile(r"[-_]sat\b", re.I), "sat"),
    (re.compile(r"\bunsat\b", re.I), "unsat"),
    (re.compile(r"\bsat\b", re.I), "sat"),
]


def _expected(name: str) -> str:
    """Filename hint → expected. Stems first (`foo-sat.cnf.dqdimacs.gz`
    has both 'sat' as a hint and 'cnf'/'dqdimacs' as suffixes)."""
    stem = name
    for ext in (".gz", ".dqdimacs", ".qdimacs", ".cnf"):
        stem = stem.removesuffix(ext)
    for pat, exp in _EXPECTED_PATTERNS:
        if pat.search(stem):
            return exp
    return "unknown"


def _problem_key(family: str, name: str) -> str:
    """Stable cross-encoding key. For test sets there's only one
    encoding per instance, so the key is just the family + stem."""
    stem = name
    for ext in (".gz", ".dqdimacs", ".qdimacs", ".cnf"):
        stem = stem.removesuffix(ext)
    return f"{family}:{stem}"


def gen_manifests(dry_run: bool = False) -> int:
    n = 0
    for variant_dir in sorted(ROOT.rglob("*")):
        if not variant_dir.is_dir() or variant_dir.name.startswith(("_", ".")):
            continue
        # Only generate for *leaf* directories (the variant level) — a
        # family dir with sub-collections shouldn't get its own manifest.
        if any(d.is_dir() and not d.name.startswith(("_", ".")) for d in variant_dir.iterdir()):
            continue
        instances = sorted(
            p
            for p in variant_dir.iterdir()
            if p.suffix in (".gz",) and ".dqdimacs" in p.name
        ) + sorted(
            p
            for p in variant_dir.iterdir()
            if p.suffix in (".dqdimacs", ".qdimacs")
        )
        if not instances:
            continue
        family = "/".join(variant_dir.relative_to(ROOT).parts)
        entries = [
            {
                "path": p.name,
                "expected": _expected(p.name),
                "problem_key": _problem_key(family, p.name),
                # Test set: no source AAG/TLSF, so HWMC/SYNTCOMP solvers
                # don't run on these (they're already DQBF/QBF).
                "source_aag": None,
                "tags": ["test", *family.split("/")],
                "params": {},
            }
            for p in instances
        ]
        mf = variant_dir / "manifest.json"
        if dry_run:
            n_e = sum(1 for e in entries if e["expected"] != "unknown")
            print(f"{family}: {len(entries)} instances ({n_e} with expected)")
        else:
            mf.write_text(json.dumps(entries, indent=2) + "\n")
            n += len(entries)
    return n


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    total = gen_manifests(dry_run=dry)
    if not dry:
        print(f"wrote manifests for {total} test instances")
