"""The §6 dependency-cycle counterexample, swept over width N.

Compiled from `tools/eqfob/examples/dep_cycle.eqfob`. UNSAT for every N
(plain FEx makes no progress; needs SFEx). Serves as the canonical
corner case for Strong Fork Extension.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import click

from core import dqdimacs
from tools.eqfob.eqfob.bitblast import bitblast
from tools.eqfob.eqfob.parse import parse
from tools.eqfob.eqfob.typecheck import check

SRC = Path(__file__).resolve().parents[3] / "tools/eqfob/examples/dep_cycle.eqfob"


@click.command()
@click.option("--out", type=click.Path(), default="benchmarks/train/dep_cycle/instances")
@click.option("-D", "widths", default="1")
def main(out: str, widths: str) -> None:
    outdir = Path(out)
    outdir.mkdir(parents=True, exist_ok=True)
    src_text = SRC.read_text()
    (outdir / "dep_cycle.eqfob").write_text(src_text)
    manifest = []
    for n in (int(x) for x in widths.split(",")):
        f = bitblast(check(parse(src_text), overrides={"N": n}))
        name = f"dep_cycle_n{n}"
        with gzip.open(outdir / f"{name}.dqdimacs.gz", "wt") as fp:
            fp.write(f"c source={SRC.name} N={n} (journal §6 cycle)\n")
            fp.write(dqdimacs.dumps(f))
        manifest.append(
            {
                "path": f"{name}.dqdimacs.gz",
                "expected": "unsat",
                "tags": ["dep_cycle"],
                "params": {"N": n},
            }
        )
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(manifest)} instances to {outdir}/")


if __name__ == "__main__":
    main()
