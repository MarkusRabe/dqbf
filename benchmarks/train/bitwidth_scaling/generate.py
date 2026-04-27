"""Generate bitwidth-scaling instances: one BV op, swept over width N.

Each instance is `∃f. ∀x[,y]. f(args) == expr(args)`, compiled to DQBF.
All instances are SAT by construction (f := the op).
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from pathlib import Path

import click

from core import dqdimacs
from tools.eqfob.eqfob.bitblast import bitblast
from tools.eqfob.eqfob.parse import parse
from tools.eqfob.eqfob.typecheck import check

OPS_UNARY = {"id": "x", "not": "~x", "inc": "x + 1"}
OPS_BINARY = {"add": "x + y", "and": "x & y", "or": "x | y", "xor": "x ^ y"}


def instances(widths: list[int]) -> Iterator[tuple[str, dict[str, int], str]]:
    for n in widths:
        for name, rhs in OPS_UNARY.items():
            yield f"{name}_n{n}", {"N": n}, _src_unary(rhs)
        for name, rhs in OPS_BINARY.items():
            yield f"{name}_n{n}", {"N": n}, _src_binary(rhs)


def _src_unary(rhs: str) -> str:
    return f"param N = 2\nfun f : bv[N] -> bv[N]\nforall x : bv[N]\nf(x) == {rhs}\n"


def _src_binary(rhs: str) -> str:
    return (
        "param N = 2\n"
        "fun f : bv[N], bv[N] -> bv[N]\n"
        "forall x : bv[N]\n"
        "forall y : bv[N]\n"
        f"f(x, y) == {rhs}\n"
    )


@click.command()
@click.option("--out", type=click.Path(), default="benchmarks/train/bitwidth_scaling/build")
@click.option("-D", "widths", default="1,2,3,4")
def main(out: str, widths: str) -> None:
    outdir = Path(out)
    outdir.mkdir(parents=True, exist_ok=True)
    ws = [int(x) for x in widths.split(",")]
    manifest = []
    for name, params, src in instances(ws):
        f = bitblast(check(parse(src), overrides=params))
        path = outdir / f"{name}.dqdimacs.gz"
        with gzip.open(path, "wt") as fp:
            fp.write(dqdimacs.dumps(f))
        manifest.append(
            {
                "path": path.name,
                "expected": "sat",
                "params": params,
                "tags": ["bitwidth_scaling", name.rsplit("_", 1)[0]],
            }
        )
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(manifest)} instances to {outdir}/")


if __name__ == "__main__":
    main()
