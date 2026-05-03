"""PEC of a tiny counter at increasing bounds.

3-bit counter with one **black-box** carry gate; the property is
"counter never reaches all-ones". Unrolled at bound k via pec2dqbf.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import click

from core import dqdimacs
from tools.pec2dqbf.aiger_seq import parse_seq_aag
from tools.pec2dqbf.encode import encode_unrolled

# 3-bit counter: latches l0,l1,l2; l0' = ¬l0; l1' = l0⊕l1; l2' = (l0∧l1)⊕l2.
# bad = l0 ∧ l1 ∧ l2. One blackbox: gate 8 = l0∧l1 (so l2's carry is unknown).
COUNTER_AAG = """\
aag 11 0 3 1 8
2 11
4 15
6 21
22
8 2 4
10 3 3
12 3 5
14 2 5
16 13 15
18 8 6
20 9 7
22 8 6
"""


@click.command()
@click.option("--out", type=click.Path(), default="benchmarks/train/pec_counter/instances")
@click.option("-D", "bounds", default="8,16,24,32,40,48,56,64,96,128")
def main(out: str, bounds: str) -> None:
    outdir = Path(out)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "counter.aag").write_text(COUNTER_AAG)
    seq = parse_seq_aag(COUNTER_AAG)
    manifest = []
    for k in (int(x) for x in bounds.split(",")):
        f = encode_unrolled(seq, k=k, blackboxes={8}, safe=False)
        name = f"counter_k{k:03d}"
        with gzip.open(outdir / f"{name}.dqdimacs.gz", "wt") as fp:
            fp.write(f"c pec2dqbf encode_unrolled k={k} blackbox=[8] source=counter.aag\n")
            fp.write(dqdimacs.dumps(f))
        manifest.append(
            {
                "path": f"{name}.dqdimacs.gz",
                "expected": "unknown",
                "tags": ["pec_counter"],
                "params": {"k": k},
            }
        )
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(manifest)} instances to {outdir}/")


if __name__ == "__main__":
    main()
