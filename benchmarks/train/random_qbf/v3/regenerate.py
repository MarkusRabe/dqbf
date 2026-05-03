"""v3 random QBF: scaled past v2 so mature DQBF solvers time out on
roughly half at the 10s budget."""

from __future__ import annotations

import json
from pathlib import Path

import click

from benchmarks.train.random_qbf.generate import QbfSpec, gen_qdimacs

SET_2QBF = [
    QbfSpec(blocks=(("a", 14), ("e", 36)), n_clauses=240, k=4, seed=30000 + s) for s in range(30)
]
SET_3QBF = [
    QbfSpec(blocks=(("e", 20), ("a", 20), ("e", 40)), n_clauses=360, k=5, seed=31000 + s)
    for s in range(30)
]


@click.command()
@click.option("--out", type=click.Path(), default="benchmarks/train/random_qbf/v3")
def main(out: str) -> None:
    base = Path(out)
    for kind, specs in {"2qbf": SET_2QBF, "3qbf": SET_3QBF}.items():
        d = base / kind
        d.mkdir(parents=True, exist_ok=True)
        m = []
        for sp in specs:
            n = f"{kind}_v3_s{sp.seed:05d}"
            (d / f"{n}.qdimacs").write_text(gen_qdimacs(sp))
            m.append(
                {
                    "path": f"{n}.qdimacs",
                    "expected": "unknown",
                    "tags": ["random_qbf_v3", kind],
                    "params": {"seed": sp.seed, "blocks": list(sp.blocks)},
                }
            )
        (d / "manifest.json").write_text(json.dumps(m, indent=2))
        print(f"{kind}: {len(m)}")


if __name__ == "__main__":
    main()
