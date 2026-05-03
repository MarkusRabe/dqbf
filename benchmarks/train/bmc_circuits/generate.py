"""BMC circuit-library benchmarks: every circuit × bitwidth N × bound k.

One subdirectory per circuit (= one family). Commits the .aag source per
(N) and the compiled .dqdimacs.gz per (N,k), with a provenance header.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import click

from core import dqdimacs
from tools.bmc2dqbf.circuits import REGISTRY
from tools.bmc2dqbf.encode import encode
from tools.pec2dqbf.aiger_seq import parse_seq_aag

WIDTHS = (2, 4, 8)
BOUNDS = (4, 8, 16)


@click.command()
@click.option("--out", type=click.Path(), default="benchmarks/train/bmc_circuits")
def main(out: str) -> None:
    base = Path(out)
    total = 0
    for name, fn in sorted(REGISTRY.items()):
        d = base / name
        d.mkdir(parents=True, exist_ok=True)
        manifest = []
        for n in WIDTHS:
            aag, comment = fn(n)
            (d / f"{name}_n{n}.aag").write_text(aag)
            seq = parse_seq_aag(aag)
            for k in BOUNDS:
                f = encode(seq, k=k, source=f"{name}_n{n}.aag")
                inst = f"{name}_n{n}_k{k:03d}"
                with gzip.open(d / f"{inst}.dqdimacs.gz", "wt") as fp:
                    fp.write(f"c bmc_circuits/{name} N={n} k={k}: {comment}\n")
                    fp.write(dqdimacs.dumps(f))
                manifest.append(
                    {
                        "path": f"{inst}.dqdimacs.gz",
                        "expected": "unknown",
                        "tags": ["bmc_circuits", name],
                        "params": {"N": n, "k": k},
                    }
                )
        (d / "manifest.json").write_text(json.dumps(manifest, indent=2))
        total += len(manifest)
        print(f"{name}: {len(manifest)} instances → {d}/")
    print(f"total: {total}")


if __name__ == "__main__":
    main()
