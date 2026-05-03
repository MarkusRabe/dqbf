from __future__ import annotations

import click

from core import dqdimacs
from tools.pec2dqbf.aiger_seq import load_seq_aag
from tools.pec2dqbf.encode import encode


@click.command()
@click.argument("aag", type=click.Path(exists=True, dir_okay=False))
@click.option("--bound", "-k", type=int, required=True)
@click.option("--mode", type=click.Choice(["unrolled", "succinct"]), default="unrolled")
@click.option("--safe/--reach-bad", default=True, help="goal = ⋀¬bad (default) vs bad_k")
@click.option("--blackbox", default="", help="comma-separated AIGER gate lhs literals")
@click.option("-o", "--out", type=click.Path(), required=True)
def main(aag: str, bound: int, mode: str, safe: bool, blackbox: str, out: str) -> None:
    circ = load_seq_aag(aag)
    bb = {int(x) for x in blackbox.split(",") if x.strip()}
    f = encode(circ, bound, blackboxes=bb, mode=mode, safe=safe, source=aag)
    with open(out, "w") as fp:
        dqdimacs.dump(f, fp)
    print(f"wrote {out}: {f.n_vars} vars, {len(f.clauses)} clauses, {len(f.universals)} universals")


if __name__ == "__main__":
    main()
