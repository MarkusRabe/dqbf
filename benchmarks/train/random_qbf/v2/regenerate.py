"""Harder random QBF: scaled so mature DQBF solvers (hqs/dqbdd/pedant)
time out on roughly half at the default 10s budget.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from benchmarks.train.random_qbf.generate import QbfSpec, gen_qdimacs

SET_2QBF = [
    QbfSpec(blocks=(("a", 12), ("e", 30)), n_clauses=200, k=4, seed=10000 + s) for s in range(50)
]
SET_3QBF = [
    QbfSpec(blocks=(("a", 14), ("e", 30), ("a", 14)), n_clauses=260, k=4, seed=11000 + s)
    for s in range(50)
]


@click.command()
@click.option("--out", type=click.Path(), default="benchmarks/train/random_qbf/v2")
def main(out: str) -> None:
    base = Path(out)
    for kind, specs in {"2qbf": SET_2QBF, "3qbf": SET_3QBF}.items():
        d = base / kind
        d.mkdir(parents=True, exist_ok=True)
        m = []
        for sp in specs:
            n = f"{kind}_v2_s{sp.seed:05d}"
            (d / f"{n}.qdimacs").write_text(gen_qdimacs(sp))
            m.append(
                {
                    "path": f"{n}.qdimacs",
                    "expected": "unknown",
                    "tags": ["random_qbf", "v2", kind],
                    "params": {"seed": sp.seed, "blocks": list(sp.blocks)},
                }
            )
        (d / "manifest.json").write_text(json.dumps(m, indent=2))
        print(f"{kind}: {len(m)}")


if __name__ == "__main__":
    main()
