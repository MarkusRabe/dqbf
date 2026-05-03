"""Encode the committed SYNTCOMP .tlsf specs via ltlsynth2dqbf at several
state-bounds so DQBF solvers can run on them and be compared against
synthesis tools (mirrors hwmcc_legacy/generate.py).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import click

from core import dqdimacs
from tools.ltlsynth2dqbf.encode import encode_tlsf
from tools.ltlsynth2dqbf.ltl import LtlParseError
from tools.ltlsynth2dqbf.tlsf import TlsfNotSupported

HERE = Path(__file__).resolve().parent / "instances"


@click.command()
@click.option("-N", "ns", default="2,4,8", help="state-bit budgets")
@click.option("-k", "--unroll", type=int, default=6)
@click.option("--max-nvars", type=int, default=200_000)
def main(ns: str, unroll: int, max_nvars: int) -> None:
    bounds = [int(x) for x in ns.split(",")]
    manifest = []
    skipped: list[tuple[str, str]] = []
    for tlsf in sorted(HERE.glob("*.tlsf")):
        text = tlsf.read_text()
        for n in bounds:
            try:
                f = encode_tlsf(text, n_states=n, k=unroll, source=tlsf.name)
            except (TlsfNotSupported, LtlParseError, ValueError) as exc:
                skipped.append((tlsf.name, str(exc)[:80]))
                break
            if f.n_vars > max_nvars:
                continue
            stem = f"{tlsf.stem}_n{n:02d}"
            with gzip.open(HERE / f"{stem}.dqdimacs.gz", "wt") as fp:
                fp.write(dqdimacs.dumps(f))
            manifest.append(
                {
                    "path": f"{stem}.dqdimacs.gz",
                    "expected": "unknown",
                    "tags": ["syntcomp_legacy"],
                    "params": {"n": n, "k": unroll, "spec": tlsf.stem},
                }
            )
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(
        f"wrote {len(manifest)} instances "
        f"({len(list(HERE.glob('*.tlsf')))} specs × bounds; {len(skipped)} skipped)"
    )
    for nm, why in skipped:
        print(f"  skip {nm}: {why}")


if __name__ == "__main__":
    main()
