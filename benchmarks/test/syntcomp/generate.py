"""Encode SYNTCOMP TLSF specs as DQBF for the test set.

Mirrors `benchmarks/train/syntcomp_legacy/generate.py`'s bounded-
synthesis encoding: ∃ a Mealy machine with `--n-states` state bits ∀
input traces of length `--unroll` such that the spec holds. SAT ⇔
realizable within the state budget.

Source: SYNTCOMP/benchmarks repo (sparse-cloned, pinned to a commit;
see `download.sh`). Only **safety** specs encode soundly (no `F/U/W`
operators) — `tools/ltlsynth2dqbf` raises `EncodingNotSound` for
liveness, which we skip rather than emit unsound instances.

`expected` is from the SYNTCOMP reference `results_verification.csv`
(the `meyerphi/syntcomp-reference` repo, pinned in `download.sh`):
- `realizable` → `unknown`. (A spec is realizable globally; bounded
  synthesis at small `--n-states` need not find a model — the bound
  can be too tight. We can't claim SAT.)
- `unrealizable` → `unsat`. (Unrealizable globally → definitely no
  bounded-state model.)
- not in the reference → `unknown`.

Usage:
    bash benchmarks/test/syntcomp/download.sh   # sparse-clone (43 MB)
    python -m benchmarks.test.syntcomp.generate
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
from pathlib import Path

import click

from core import dqdimacs
from tools.ltlsynth2dqbf.encode import EncodingNotSound, encode_tlsf
from tools.ltlsynth2dqbf.ltl import LtlParseError
from tools.ltlsynth2dqbf.tlsf import TlsfNotSupported

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INSTANCES = HERE / "instances"
RESULTS_CSV = ROOT / "benchmarks" / "_downloads" / "syntcomp_results.csv"


def _load_results() -> dict[str, str]:
    """Stem → 'realizable'/'unrealizable' from the SYNTCOMP reference."""
    out: dict[str, str] = {}
    if not RESULTS_CSV.exists():
        print(f"warning: {RESULTS_CSV} missing; all expected=unknown", file=sys.stderr)
        return out
    with RESULTS_CSV.open() as f:
        for row in csv.DictReader(f):
            out[row["specification"]] = row["realizability_status"]
    return out


def _expected(realizability: str | None) -> str:
    # Bounded synthesis with a *fixed* state budget: realizable globally
    # need not imply a model with ≤n states exists. Only `unrealizable`
    # gives a usable verdict.
    if realizability == "unrealizable":
        return "unsat"
    return "unknown"


@click.command()
@click.option("--out", type=click.Path(), default=str(HERE))
@click.option("--n-instances", default=50, help="how many encodable specs to emit")
@click.option("-N", "ns", default="2,4,8", help="state-bit budgets")
@click.option("-k", "--unroll", type=int, default=6)
@click.option("--max-vars", default=80_000)
def main(out: str, n_instances: int, ns: str, unroll: int, max_vars: int) -> None:
    base = Path(out)
    bounds = [int(x) for x in ns.split(",")]
    tlsfs = sorted(INSTANCES.rglob("*.tlsf"), key=lambda p: p.stat().st_size)
    if not tlsfs:
        print("no .tlsf under instances/ — run download.sh first", file=sys.stderr)
        sys.exit(1)
    results = _load_results()
    manifests: dict[str, list[dict]] = {}
    skipped: dict[str, int] = {}
    n_ok = total = 0
    src_dir = base / "bounded" / "tlsf"
    src_dir.mkdir(parents=True, exist_ok=True)

    for tlsf in tlsfs:
        if n_ok >= n_instances:
            break
        text = tlsf.read_text()
        name = tlsf.stem
        # Encode-test at the smallest bound first; skip the spec entirely
        # if it can't encode (liveness/unsupported).
        try:
            encode_tlsf(text, n_states=bounds[0], k=unroll, source=tlsf.name)
        except (EncodingNotSound, TlsfNotSupported, LtlParseError, ValueError) as exc:
            skipped[type(exc).__name__] = skipped.get(type(exc).__name__, 0) + 1
            continue
        n_ok += 1
        # Commit the .tlsf source so `_find_source_tlsf` and `strix` can
        # find it.
        (src_dir / tlsf.name).write_text(text)
        realizability = results.get(name)
        pkey = f"syntcomp:{name}"
        for n in bounds:
            try:
                f = encode_tlsf(text, n_states=n, k=unroll, source=tlsf.name)
            except (EncodingNotSound, TlsfNotSupported, LtlParseError, ValueError):
                continue
            if f.n_vars > max_vars:
                continue
            d = base / "bounded" / name
            d.mkdir(parents=True, exist_ok=True)
            inst = f"{name}_n{n:02d}"
            with gzip.open(d / f"{inst}.dqdimacs.gz", "wt") as fp:
                fp.write(
                    f"c syntcomp/{name} bounded-synthesis n_states={n} k={unroll} "
                    f"realizability={realizability or '?'}\n"
                )
                fp.write(dqdimacs.dumps(f))
            manifests.setdefault(name, []).append(
                {
                    "path": f"{inst}.dqdimacs.gz",
                    "expected": _expected(realizability),
                    "problem_key": pkey,
                    "source_aag": None,
                    "source_tlsf": f"../tlsf/{tlsf.name}",
                    "tags": ["syntcomp", name, "bounded"],
                    "params": {
                        "n_states": n,
                        "k": unroll,
                        "realizability": realizability,
                    },
                }
            )
            total += 1
    for name, mf in manifests.items():
        (base / "bounded" / name / "manifest.json").write_text(json.dumps(mf, indent=2) + "\n")
    print(f"wrote {total} test instances ({n_ok} specs, skipped: {skipped})")


if __name__ == "__main__":
    main()
