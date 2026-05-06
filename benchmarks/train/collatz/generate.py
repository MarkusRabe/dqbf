"""Collatz conjecture as bounded reachability.

Two encodings, both compiled from EQFOB:

- ``unrolled``: ∀x. ∃s_0..s_K. trajectory + reach-1 within K explicit steps
  (∀∃ QBF; K is the literal number of steps).
- ``succinct``: ∃f: bv[N]×bv[K]→bv[N]. ∀x. ∀t. f(x,0)=x ∧
  (t+1≠0 → f(x,t+1)=step(f(x,t))) ∧ (t+1=0 → f(x,t)=1)
  (genuine DQBF; the step counter is K bits, so the bound is 2^K-1 steps).

The step function fixes 0 and 1 to 1 (sticky sink) and otherwise applies
v/2 (logical) or 3v+1. Arithmetic is modular at width N, so this is the
*N-bit modular* Collatz, not the integer conjecture — see README.
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

PAIRS: list[tuple[int, int]] = [(8, 6), (12, 8), (16, 10), (24, 12)]


def step_expr(v: str) -> str:
    return f"ite({v} <= 1, ({v} & 0) + 1, ite(({v} & 1) == 0, {v} >>> 1, 3 * {v} + 1))"


def eqfob_unrolled(n: int, k: int) -> str:
    lines = [
        f"-- Collatz unrolled BMC: every nonzero {n}-bit start reaches 1 in <= {k} steps?",
        "-- SAT iff yes (UNSAT expected for small K -- many starts need more steps).",
        f"param N = {n}",
        "forall x : bv[N]",
    ]
    lines += [f"exists s{i} : bv[N]" for i in range(k + 1)]
    lines.append("s0 == x")
    for i in range(k):
        lines.append(f"s{i + 1} == {step_expr(f's{i}')}")
    reach = " || ".join(f"(s{i} == 1)" for i in range(k + 1))
    lines.append(f"(x == 0) || {reach}")
    return "\n".join(lines) + "\n"


def eqfob_succinct(n: int, k: int) -> str:
    fxt = "f(x, t)"
    return (
        "\n".join(
            [
                f"-- Collatz succinct DQBF: trajectory f(x,.) over 2^{k}-1 steps reaches 1?",
                "-- ∃f. ∀x,t. f(x,0)=x ∧ transition ∧ (t=max → f(x,t)=1). SAT iff bound suffices.",
                f"param N = {n}",
                f"param K = {k}",
                "fun f : bv[N], bv[K] -> bv[N]",
                "forall x : bv[N]",
                "forall t : bv[K]",
                "x == f(x, 0)",
                f"((t + 1) != 0) -> (f(x, t + 1) == {step_expr(fxt)})",
                "((t + 1) == 0) -> ((x == 0) || (f(x, t) == 1))",
            ]
        )
        + "\n"
    )


ENCODINGS = {"unrolled": eqfob_unrolled, "succinct": eqfob_succinct}


@click.command()
@click.option("--out", type=click.Path(), default="benchmarks/test/collatz")
def main(out: str) -> None:
    base = Path(out)
    base.mkdir(parents=True, exist_ok=True)
    manifest = []
    for enc, gen in ENCODINGS.items():
        for n, k in PAIRS:
            name = f"collatz_{enc}_n{n:02d}_k{k:02d}"
            src = gen(n, k)
            (base / f"{name}.eqfob").write_text(src)
            f = bitblast(check(parse(src)))
            with gzip.open(base / f"{name}.dqdimacs.gz", "wt") as fp:
                fp.write(
                    f"c benchmarks/test/collatz/generate.py enc={enc} N={n} K={k}\n"
                    f"c source={name}.eqfob\n"
                )
                fp.write(dqdimacs.dumps(f))
            manifest.append(
                {
                    "path": f"{name}.dqdimacs.gz",
                    "expected": "unknown",
                    "tags": ["collatz", enc],
                    "params": {"N": n, "K": k, "encoding": enc},
                }
            )
            print(f"{name}: {f.n_vars} vars, {len(f.clauses)} clauses")
    (base / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(manifest)} instances to {base}/")


if __name__ == "__main__":
    main()
