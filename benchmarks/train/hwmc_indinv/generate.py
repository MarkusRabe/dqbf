"""Inductive-invariant search benchmarks: each circuit × bitwidth N.

One DQDIMACS per (circuit-variant, N). Unlike `bmc_circuits/` there is
no bound parameter: the invariant search is unbounded by construction.

Variants and expected results (by construction — see
`tools/hwmc2dqbf_indinv/encode.py` for the SAT/UNSAT semantics flip):

  mutex, fifo1, alu_add        bad unreachable  → SAT
  mutex/fifo1/alu_add _buggy   fault injected   → UNSAT
  counter, gray, shift_reg     bad reachable    → UNSAT
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import click

from core import dqdimacs
from tools.bmc2dqbf.circuits import REGISTRY
from tools.hwmc2dqbf_indinv.circuits_buggy import REGISTRY_BUGGY
from tools.hwmc2dqbf_indinv.encode import encode_indinv_aig
from tools.pec2dqbf.aiger_seq import parse_seq_aag

WIDTHS = (2, 4, 8, 16, 32)

# By construction (see circuit docstrings in tools/bmc2dqbf/circuits.py):
EXPECTED = {
    "mutex": "sat",
    "fifo1": "sat",
    "alu_add": "sat",
    "counter": "unsat",
    "gray": "unsat",
    "shift_reg": "unsat",
    "mutex_buggy": "unsat",
    "fifo1_buggy": "unsat",
    "alu_add_buggy": "unsat",
}


@click.command()
@click.option("--out", type=click.Path(), default="benchmarks/train/hwmc_indinv/inductive")
@click.option("-N", "widths", default=",".join(str(w) for w in WIDTHS))
def main(out: str, widths: str) -> None:
    base = Path(out)
    base.mkdir(parents=True, exist_ok=True)
    ws = [int(x) for x in widths.split(",")]
    manifest = []
    for name, fn in sorted({**REGISTRY, **REGISTRY_BUGGY}.items()):
        for n in ws:
            aag, comment = fn(n)
            (base / f"{name}_n{n}.aag").write_text(aag)
            seq = parse_seq_aag(aag)
            f = encode_indinv_aig(seq, source=f"{name}_n{n}.aag")
            inst = f"indinv_{name}_n{n}"
            with gzip.open(base / f"{inst}.dqdimacs.gz", "wt") as fp:
                fp.write(f"c hwmc_indinv N={n}: {comment}\n")
                fp.write(dqdimacs.dumps(f))
            manifest.append(
                {
                    "path": f"{inst}.dqdimacs.gz",
                    "expected": EXPECTED[name],
                    "problem_key": f"hwmc_indinv:{name}:{n}",
                    # DQBF SAT here = invariant exists = bad UNREACHABLE,
                    # which abc-pdr reports as UNSAT (no counterexample).
                    "source_polarity": "inverted",
                    "tags": ["hwmc_indinv", name],
                    "params": {"N": n, "circuit": name},
                }
            )
    (base / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"{len(manifest)} instances → {base}/")


if __name__ == "__main__":
    main()
