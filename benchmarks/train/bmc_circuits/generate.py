"""BMC circuit-library benchmarks: every circuit × bitwidth N × bound k.

One subdirectory per circuit (= one family). Commits the .aag source per
(N) and the compiled .dqdimacs.gz per (N,k), with a provenance header.

Two modes:
  unrolled (default) — `tools.bmc2dqbf.encode.encode`, O(k·|circuit|) vars
  succinct           — `encode_succinct`, latches as ∃-functions of a
                       universal step counter; O(|circuit|+log k) vars
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import click

from core import dqdimacs
from tools.bmc2dqbf.circuits import REGISTRY
from tools.bmc2dqbf.encode import encode, encode_succinct
from tools.pec2dqbf.aiger_seq import parse_seq_aag

WIDTHS = (2, 4, 8, 16, 32)
BOUNDS = (8, 16, 32, 64, 128)

ENCODERS = {"unrolled": encode, "succinct": encode_succinct}


@click.command()
@click.option("--out", type=click.Path(), default="benchmarks/train/bmc_circuits")
@click.option("--mode", type=click.Choice(sorted(ENCODERS)), default="unrolled")
@click.option("-N", "widths", default=",".join(str(w) for w in WIDTHS))
@click.option("-K", "bounds", default=",".join(str(k) for k in BOUNDS))
def main(out: str, mode: str, widths: str, bounds: str) -> None:
    base = Path(out)
    enc = ENCODERS[mode]
    ws = [int(x) for x in widths.split(",")]
    ks = [int(x) for x in bounds.split(",")]
    total = 0
    for name, fn in sorted(REGISTRY.items()):
        d = base / name
        d.mkdir(parents=True, exist_ok=True)
        manifest = []
        for n in ws:
            aag, comment = fn(n)
            (d / f"{name}_n{n}.aag").write_text(aag)
            seq = parse_seq_aag(aag)
            for k in ks:
                f = enc(seq, k=k, source=f"{name}_n{n}.aag")
                inst = f"{name}_n{n}_k{k:03d}"
                with gzip.open(d / f"{inst}.dqdimacs.gz", "wt") as fp:
                    fp.write(f"c bmc_circuits/{name} mode={mode} N={n} k={k}: {comment}\n")
                    fp.write(dqdimacs.dumps(f))
                manifest.append(
                    {
                        "path": f"{inst}.dqdimacs.gz",
                        "expected": "unknown",
                        "tags": ["bmc_circuits", name, mode],
                        "params": {"N": n, "k": k, "mode": mode},
                    }
                )
        (d / "manifest.json").write_text(json.dumps(manifest, indent=2))
        total += len(manifest)
        print(f"{name}: {len(manifest)} instances → {d}/")
    print(f"total: {total}")


if __name__ == "__main__":
    main()
