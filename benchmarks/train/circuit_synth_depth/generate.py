"""Minimal-depth circuit-synthesis benchmarks.

Gates are arranged in `d` layers of width `w = max(n_inputs, n_outputs)`
so the gate budget is non-binding and depth is the constraint. Sweep
d ∈ {opt−1, opt} when the depth optimum is known, otherwise
{⌈upper/2⌉, upper}.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import click

from core import dqdimacs
from tools.circuitsynth2dqbf.encode import encode_depth
from tools.circuitsynth2dqbf.spec_functions import REGISTRY, WIDTH_CAP, WIDTHS

VAR_CAP = 50_000


def d_sweep(known: int | None, upper: int) -> list[tuple[int, str]]:
    if known is not None:
        return [(known - 1, "unsat"), (known, "sat")]
    mid = max(1, upper // 2)
    return [(mid, "unknown"), (upper, "sat")]


@click.command()
@click.option("--out", default="benchmarks/train/circuit_synth_depth/instances")
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
            w = max(spec.n_inputs, spec.n_outputs)
            for d, expect in d_sweep(spec.known_depth, spec.upper_depth):
                if d < 0:
                    continue
                try:
                    f = encode_depth(spec, d, w)
                except ValueError as e:
                    skipped.append(f"{spec.name}_d{d}: {e}")
                    continue
                if f.n_vars > VAR_CAP:
                    skipped.append(f"{spec.name}_d{d}: {f.n_vars} vars > {VAR_CAP}")
                    continue
                inst = f"csd_{spec.name}_d{d:02d}_w{w:02d}"
                manifest.append(
                    {
                        "name": inst,
                        "expected": expect,
                        "n_vars": f.n_vars,
                        "n_clauses": len(f.clauses),
                        "params": {"spec": spec.name, "depth": d, "width": w, "n": n},
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
