"""Invertibility-condition instances: ∃f. ∀x. op(f(x), x) == c.

Each template asks whether `op` admits a left-inverse-like witness `f`.
SAT/UNSAT is determined by the algebraic structure of `op` (independent
of N≥2), so `expected` is set by construction.
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

# (name, constraint-body, expected)
TEMPLATES: list[tuple[str, str, str]] = [
    # SAT — explicit witnesses exist
    ("add_zero", "(f(x) + x) == 0", "sat"),  # f(x) = ~x + 1
    ("xor_const", "(f(x) ^ x) == 1", "sat"),  # f(x) = x ^ 1
    ("and_x", "(f(x) & x) == x", "sat"),  # f(x) = x (or all-ones)
    ("or_x", "(f(x) | x) == x", "sat"),  # f(x) = 0
    # UNSAT — pigeonhole on some bit / some x
    ("or_zero", "(f(x) | x) == 0", "unsat"),  # fails for any x≠0
    ("and_notx", "(f(x) & x) == ~x", "unsat"),  # bit i: needs x_i ∧ ¬x_i
    ("and_one", "(f(x) & x) == 1", "unsat"),  # fails at x=0
    ("shl_x", "(f(x) << 1) == x", "unsat"),  # fails when x bit0 = 1
]


def _src(body: str) -> str:
    return f"param N = 4\nfun f : bv[N] -> bv[N]\nforall x : bv[N]\n{body}\n"


@click.command()
@click.option(
    "--out", type=click.Path(), default="benchmarks/train/synthesis_invertibility/instances"
)
@click.option("-D", "widths", default="4,8,16")
def main(out: str, widths: str) -> None:
    outdir = Path(out)
    outdir.mkdir(parents=True, exist_ok=True)
    ws = [int(x) for x in widths.split(",")]
    manifest = []
    for n in ws:
        for name, body, expected in TEMPLATES:
            stem = f"{name}_n{n}"
            src = _src(body)
            (outdir / f"{stem}.eqfob").write_text(src)
            f = bitblast(check(parse(src), overrides={"N": n}))
            with gzip.open(outdir / f"{stem}.dqdimacs.gz", "wt") as fp:
                fp.write(
                    "c synthesis_invertibility/generate.py "
                    f"template={name} N={n} source={stem}.eqfob\n"
                )
                fp.write(dqdimacs.dumps(f))
            manifest.append(
                {
                    "path": f"{stem}.dqdimacs.gz",
                    "expected": expected,
                    "tags": ["synthesis_invertibility", name],
                    "params": {"N": n, "template": name},
                }
            )
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    sat = sum(1 for m in manifest if m["expected"] == "sat")
    print(f"wrote {len(manifest)} instances ({sat} sat / {len(manifest) - sat} unsat) to {outdir}/")


if __name__ == "__main__":
    main()
