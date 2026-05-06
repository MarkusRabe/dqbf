"""Minimal-circuit synthesis benchmarks (gates/ and depth/ variants).

For each (function, bitwidth) emit instances around the known/estimated
optimum so the family contains both SAT (a circuit exists) and UNSAT (a
lower-bound proof) verdicts. ``expected`` is set only when derivable
from a known optimum.

- ``gates/``  — ∃ a B₂ circuit with ≤k gates computing f
- ``depth/``  — ∃ a B₂ circuit with ≤d layers (width = max(in, out))
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import click

from core import dqdimacs
from core.formula import Formula
from tools.circuitsynth2dqbf.encode import encode_depth, encode_gates
from tools.circuitsynth2dqbf.spec_functions import REGISTRY, WIDTH_CAP, WIDTHS, Spec

VAR_CAP = 50_000


def k_sweep(known: int | None, upper: int) -> list[tuple[int, str]]:
    if known is not None:
        return [(known - 1, "unsat"), (known, "sat"), (known + 1, "sat")]
    mid = max(1, upper // 2)
    return [(mid, "unknown"), (upper, "sat"), (upper + 2, "sat")]


def d_sweep(known: int | None, upper: int) -> list[tuple[int, str]]:
    if known is not None:
        return [(known - 1, "unsat"), (known, "sat")]
    mid = max(1, upper // 2)
    return [(mid, "unknown"), (upper, "sat")]


def _gates(spec: Spec) -> list[tuple[str, str, dict, Formula]]:
    out: list[tuple[str, str, dict, Formula]] = []
    for k, expect in k_sweep(spec.known_gates, spec.upper_gates):
        if k < 0:
            continue
        out.append(
            (f"csg_{spec.name}_k{k:03d}", expect, {"k": k}, encode_gates(spec, k))
        )
    return out


def _depth(spec: Spec) -> list[tuple[str, str, dict, Formula]]:
    out: list[tuple[str, str, dict, Formula]] = []
    w = max(spec.n_inputs, spec.n_outputs)
    for d, expect in d_sweep(spec.known_depth, spec.upper_depth):
        if d < 0:
            continue
        out.append(
            (
                f"csd_{spec.name}_d{d:02d}_w{w:02d}",
                expect,
                {"depth": d, "width": w},
                encode_depth(spec, d, w),
            )
        )
    return out


VARIANTS = {"gates": _gates, "depth": _depth}


@click.command()
@click.option("--out", default="benchmarks/train/circuit_synth")
@click.option("--dry-run", is_flag=True)
def main(out: str, dry_run: bool) -> None:
    base = Path(out)
    for variant, build in VARIANTS.items():
        d = base / variant
        d.mkdir(parents=True, exist_ok=True)
        manifest: list[dict] = []
        skipped: list[str] = []
        for fname, builder in sorted(REGISTRY.items()):
            cap = WIDTH_CAP.get(fname, max(WIDTHS))
            for n in (w for w in WIDTHS if w <= cap):
                spec = builder(n)
                try:
                    insts = build(spec)
                except ValueError as e:
                    skipped.append(f"{spec.name}: {e}")
                    continue
                for inst, expect, params, f in insts:
                    if f.n_vars > VAR_CAP:
                        skipped.append(f"{inst}: {f.n_vars} vars > {VAR_CAP}")
                        continue
                    manifest.append(
                        {
                            "path": f"{inst}.dqdimacs.gz",
                            "expected": expect,
                            "n_vars": f.n_vars,
                            "n_clauses": len(f.clauses),
                            "params": {"spec": spec.name, "n": n, **params},
                        }
                    )
                    if not dry_run:
                        with gzip.open(d / f"{inst}.dqdimacs.gz", "wt") as fp:
                            dqdimacs.dump(f, fp)
        (d / "manifest.json").write_text(json.dumps(manifest, indent=2))
        print(f"{variant}: {len(manifest)} instances; {len(skipped)} skipped")
        for s in skipped:
            print(f"  skip: {s}")


if __name__ == "__main__":
    main()
