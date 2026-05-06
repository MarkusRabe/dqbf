"""Random QBF generator (Chen-Interian-style).

Emits QDIMACS, which is a strict subset of DQDIMACS (only `a`/`e`
prefix lines), so any DQBF solver consumes them and we can cross-check
against established QBF solvers (cadet, caqe, rareqs).

The clause/variable ratios below are tuned so the SAT/UNSAT split is
roughly even on the fixed sizes used for the static benchmark set.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

import click


@dataclass(frozen=True)
class QbfSpec:
    blocks: tuple[tuple[str, int], ...]  # e.g. (("a", 4), ("e", 8)) for 2QBF
    n_clauses: int
    k: int  # literals per clause
    seed: int

    @property
    def n_vars(self) -> int:
        return sum(n for _, n in self.blocks)


def gen_qdimacs(spec: QbfSpec) -> str:
    rnd = random.Random(spec.seed)
    var = 1
    prefix: list[str] = []
    block_vars: list[tuple[str, list[int]]] = []
    for q, n in spec.blocks:
        vs = list(range(var, var + n))
        block_vars.append((q, vs))
        prefix.append(f"{q} " + " ".join(str(v) for v in vs) + " 0")
        var += n
    nv = var - 1
    # Chen-Interian: each clause draws a fixed number of literals from each
    # block (here: 1 universal + (k-1) existentials for 2QBF; uniform for >2).
    clauses: list[str] = []
    if len(block_vars) == 2 and block_vars[0][0] == "a":
        au, ae = block_vars[0][1], block_vars[1][1]
        for _ in range(spec.n_clauses):
            us = rnd.sample(au, k=min(1, len(au)))
            es = rnd.sample(ae, k=spec.k - len(us))
            lits = [v * rnd.choice((-1, 1)) for v in us + es]
            clauses.append(" ".join(str(x) for x in lits) + " 0")
    else:
        allv = list(range(1, nv + 1))
        for _ in range(spec.n_clauses):
            lits = [v * rnd.choice((-1, 1)) for v in rnd.sample(allv, k=spec.k)]
            clauses.append(" ".join(str(x) for x in lits) + " 0")
    body = "\n".join(prefix + clauses)
    return (
        f"c random_qbf seed={spec.seed} blocks={spec.blocks}\np cnf {nv} {spec.n_clauses}\n{body}\n"
    )


# --- static benchmark set -------------------------------------------------
# One generator emits all difficulty tiers to {2qbf,3qbf}/. Tiers are a
# parameter sweep (clause/var count), not a separate encoding, so they
# share a directory; the seed ranges are disjoint so filenames don't
# collide.

SET_2QBF = (
    # tiny — ~half SAT (verified with caqe/semantics)
    [QbfSpec(blocks=(("a", 3), ("e", 6)), n_clauses=18, k=3, seed=s) for s in range(100)]
    # medium — mature DQBF solvers time out on roughly half at 10 s
    + [
        QbfSpec(blocks=(("a", 12), ("e", 30)), n_clauses=200, k=4, seed=10000 + s)
        for s in range(50)
    ]
    # hard — most DQBF solvers time out
    + [
        QbfSpec(blocks=(("a", 14), ("e", 36)), n_clauses=240, k=4, seed=30000 + s)
        for s in range(30)
    ]
)
SET_3QBF = (
    [
        QbfSpec(blocks=(("a", 2), ("e", 4), ("a", 2)), n_clauses=12, k=3, seed=1000 + s)
        for s in range(50)
    ]
    + [
        QbfSpec(blocks=(("e", 3), ("a", 2), ("e", 4)), n_clauses=13, k=3, seed=2000 + s)
        for s in range(50)
    ]
    + [
        QbfSpec(blocks=(("a", 14), ("e", 30), ("a", 14)), n_clauses=260, k=4, seed=11000 + s)
        for s in range(50)
    ]
    + [
        QbfSpec(blocks=(("e", 20), ("a", 20), ("e", 40)), n_clauses=360, k=5, seed=31000 + s)
        for s in range(30)
    ]
)


@click.command()
@click.option("--out", type=click.Path(), default="benchmarks/train/random_qbf")
@click.option("--two-qbf-only", is_flag=True, help="emit only the ∀∃ subset (cadet-compatible)")
def main(out: str, two_qbf_only: bool) -> None:
    base = Path(out)
    families = {"2qbf": SET_2QBF, "3qbf": ([] if two_qbf_only else SET_3QBF)}
    total = 0
    for kind, specs in families.items():
        if not specs:
            continue
        outdir = base / kind
        outdir.mkdir(parents=True, exist_ok=True)
        manifest = []
        for spec in specs:
            name = f"{kind}_s{spec.seed:05d}"
            (outdir / f"{name}.qdimacs").write_text(gen_qdimacs(spec))
            manifest.append(
                {
                    "path": f"{name}.qdimacs",
                    "expected": "unknown",
                    "tags": ["random_qbf", kind],
                    "params": {
                        "seed": spec.seed,
                        "blocks": list(spec.blocks),
                        "n_clauses": spec.n_clauses,
                        "k": spec.k,
                    },
                }
            )
        (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        total += len(manifest)
        print(f"wrote {len(manifest)} instances to {outdir}/")
    print(f"total: {total}")


if __name__ == "__main__":
    main()
