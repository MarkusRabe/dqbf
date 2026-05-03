"""Encode the committed HWMCC'17 .aag circuits via bmc2dqbf at several
bounds so DQBF solvers can run on them and be compared against abc.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import click

from core import dqdimacs
from tools.bmc2dqbf.encode import encode
from tools.pec2dqbf.aiger_seq import parse_seq_aag

HERE = Path(__file__).resolve().parent / "instances"


@click.command()
@click.option("-K", "ks", default="10,50,100,1000")
@click.option("--max-nvars", default=10_000_000, help="skip (circuit,k) if it would exceed this")
def main(ks: str, max_nvars: int) -> None:
    bounds = [int(x) for x in ks.split(",")]
    manifest = []
    for aag in sorted(HERE.glob("*.aag")):
        seq = parse_seq_aag(aag.read_text())
        nstep = len(seq.inputs) + len(seq.latches) + len(seq.gates)
        for k in bounds:
            if (k + 1) * nstep > max_nvars:
                continue
            f = encode(seq, k=k, safe=False, source=aag.name)
            stem = f"{aag.stem}_k{k:04d}"
            with gzip.open(HERE / f"{stem}.dqdimacs.gz", "wt") as fp:
                fp.write(dqdimacs.dumps(f))
            manifest.append(
                {
                    "path": f"{stem}.dqdimacs.gz",
                    "expected": "unknown",
                    "tags": ["hwmcc_legacy"],
                    "params": {"k": k, "circuit": aag.stem},
                }
            )
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(manifest)} instances ({len(list(HERE.glob('*.aag')))} circuits × bounds)")


if __name__ == "__main__":
    main()
