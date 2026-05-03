"""BMC of the parametric fixed-priority mutex from
`tools/bmc2dqbf/circuits.py`, swept over (n requesters × bound k).

The property is mutual exclusion (≤1 grant); the arbiter is correct by
construction, so every instance is UNSAT (safe).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import click

from core import dqdimacs
from tools.bmc2dqbf.circuits import circuit_mutex
from tools.bmc2dqbf.encode import encode
from tools.pec2dqbf.aiger_seq import parse_seq_aag


@click.command()
@click.option("--out", type=click.Path(), default="benchmarks/train/bmc_mutex/instances")
@click.option("-N", "ns", default="2,4,8,16,32")
@click.option("-K", "ks", default="8,16,32,64,128")
def main(out: str, ns: str, ks: str) -> None:
    outdir = Path(out)
    outdir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for n in (int(x) for x in ns.split(",")):
        aag, comment = circuit_mutex(n)
        (outdir / f"mutex_n{n}.aag").write_text(aag)
        seq = parse_seq_aag(aag)
        for k in (int(x) for x in ks.split(",")):
            stem = f"mutex_n{n}_k{k:03d}"
            f = encode(seq, k=k, safe=False, source=f"mutex_n{n}.aag")
            with gzip.open(outdir / f"{stem}.dqdimacs.gz", "wt") as fp:
                fp.write(f"c bmc2dqbf encode n={n} k={k} safe=False source=mutex_n{n}.aag\n")
                fp.write(f"c circuit: {comment}\n")
                fp.write(dqdimacs.dumps(f))
            manifest.append(
                {
                    "path": f"{stem}.dqdimacs.gz",
                    "expected": "unsat",
                    "tags": ["bmc_mutex"],
                    "params": {"n": n, "k": k},
                }
            )
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(manifest)} instances to {outdir}/")


if __name__ == "__main__":
    main()
