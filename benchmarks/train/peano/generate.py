"""Peano-style recursive definitions of + and × over bv[N], as DQBF synthesis.

Given only `inc(x) = x+1`, ask the solver to find a binary function
satisfying the Peano recursion. Three problems, each SAT (the cert IS
the operation), each scalable in N:

  add:   ∃add. ∀a b.  add(a,0)==a  ∧  add(a, b+1) == add(a,b)+1
  mul:   ∃mul. ∀a b.  mul(a,0)==0  ∧  mul(a, b+1) == mul(a,b)+a
  both:  ∃add,mul. ∀a b.  (add axioms)  ∧  mul(a,0)==0
                          ∧  mul(a, b+1) == add(mul(a,b), a)

Under bv[N] arithmetic the recursion at b=max wraps to b+1=0, which is
consistent with mod-2^N + and × — so the axioms are exactly satisfiable
by the standard operations.
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

ADD = """\
param N = {N}
fun add : bv[N], bv[N] -> bv[N]
forall a : bv[N]
forall b : bv[N]
a == add(a, 0)
(add(a, b) + 1) == add(a, b + 1)
"""

MUL = """\
param N = {N}
fun mul : bv[N], bv[N] -> bv[N]
forall a : bv[N]
forall b : bv[N]
0 == mul(a, 0)
(mul(a, b) + a) == mul(a, b + 1)
"""

BOTH = """\
param N = {N}
fun add : bv[N], bv[N] -> bv[N]
fun mul : bv[N], bv[N] -> bv[N]
forall a : bv[N]
forall b : bv[N]
a == add(a, 0)
(add(a, b) + 1) == add(a, b + 1)
0 == mul(a, 0)
add(mul(a, b), a) == mul(a, b + 1)
"""

V2_ADD = """\
param N = {N}
fun s : bv[N] -> bv[N]
fun add : bv[N], bv[N] -> bv[N]
forall a : bv[N]
forall b : bv[N]
(a + 1) == s(a)
a == add(a, 0)
s(add(a, b)) == add(a, s(b))
"""

V2_MUL = """\
param N = {N}
fun s : bv[N] -> bv[N]
fun mul : bv[N], bv[N] -> bv[N]
forall a : bv[N]
forall b : bv[N]
(a + 1) == s(a)
0 == mul(a, 0)
(mul(a, b) + a) == mul(a, s(b))
"""

V2_BOTH = """\
param N = {N}
fun s : bv[N] -> bv[N]
fun add : bv[N], bv[N] -> bv[N]
fun mul : bv[N], bv[N] -> bv[N]
forall a : bv[N]
forall b : bv[N]
(a + 1) == s(a)
a == add(a, 0)
s(add(a, b)) == add(a, s(b))
0 == mul(a, 0)
add(mul(a, b), a) == mul(a, s(b))
"""

PROBLEMS = {
    "add": ADD,
    "mul": MUL,
    "both": BOTH,
    "v2_add": V2_ADD,
    "v2_mul": V2_MUL,
    "v2_both": V2_BOTH,
}


@click.command()
@click.option("--out", type=click.Path(), default="benchmarks/train/peano/instances")
@click.option("-D", "widths", default="2,3,4,5,6,8")
def main(out: str, widths: str) -> None:
    outdir = Path(out)
    outdir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for kind, tmpl in PROBLEMS.items():
        for n in (int(x) for x in widths.split(",")):
            src = tmpl.format(N=n)
            (outdir / f"peano_{kind}_n{n}.eqfob").write_text(src)
            f = bitblast(check(parse(src)))
            name = f"peano_{kind}_n{n}"
            with gzip.open(outdir / f"{name}.dqdimacs.gz", "wt") as fp:
                fp.write(f"c benchmarks/train/peano/generate.py kind={kind} N={n}\n")
                fp.write(f"c source={name}.eqfob\n")
                fp.write(dqdimacs.dumps(f))
            manifest.append(
                {
                    "path": f"{name}.dqdimacs.gz",
                    "expected": "sat",
                    "tags": ["peano", kind],
                    "params": {"N": n, "kind": kind},
                }
            )
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(manifest)} instances to {outdir}/")


if __name__ == "__main__":
    main()
