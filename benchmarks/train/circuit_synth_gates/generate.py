"""Minimal-gate-count circuit-synthesis benchmarks.

For each (function, bitwidth) emit instances at k ∈ {opt−1, opt, opt+1}
when the B₂ optimum is known, otherwise a small sweep around the
trivial upper bound. SAT ⇒ a circuit of k gates exists; UNSAT ⇒ none
does (a lower bound). `expected` is set only when derivable from a
known optimum.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import click

from core import dqdimacs
from tools.circuitsynth2dqbf.encode import encode_gates
from tools.circuitsynth2dqbf.spec_functions import REGISTRY, WIDTH_CAP, WIDTHS

VAR_CAP = 50_000


def k_sweep(known: int | None, upper: int) -> list[tuple[int, str]]:
    if known is not None:
        return [(known - 1, "unsat"), (known, "sat"), (known + 1, "sat")]
    mid = max(1, upper // 2)
    return [(mid, "unknown"), (upper, "sat"), (upper + 2, "sat")]


@click.command()
@click.option("--out", default="benchmarks/train/circuit_synth_gates/instances")
@click.option("--dry-run", is_flag=True)
def main(out: str, dry_run: bool) -> None:
    base = Path(out)
    base.mkdir(parents=True, exist_ok=True)
    manifest = []
    skipped: list[str] = []
    for fname, builder in sorted(REGISTRY.items()):
        cap = WIDTH_CAP.get(fname, max(WIDTHS))
        for n in WIDTHS:
            if n > cap:
                continue
            spec = builder(n)
            for k, expect in k_sweep(spec.known_gates, spec.upper_gates):
                if k < 0:
                    continue
                try:
                    f = encode_gates(spec, k)
                except ValueError as e:
                    skipped.append(f"{spec.name}_k{k}: {e}")
                    continue
                if f.n_vars > VAR_CAP:
                    skipped.append(f"{spec.name}_k{k}: {f.n_vars} vars > {VAR_CAP}")
                    continue
                inst = f"csg_{spec.name}_k{k:03d}"
                manifest.append(
                    {
                        "name": inst,
                        "expected": expect,
                        "n_vars": f.n_vars,
                        "n_clauses": len(f.clauses),
                        "params": {"spec": spec.name, "k": k, "n": n},
                    }
                )
                if not dry_run:
                    with gzip.open(base / f"{inst}.dqdimacs.gz", "wt") as fp:
                        dqdimacs.dump(f, fp)
    (base / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"{len(manifest)} instances; {len(skipped)} skipped")
    for s in skipped:
        print(f"  skip: {s}")


if __name__ == "__main__":
    main()
