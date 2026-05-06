"""Conjunction-of-K independent sub-formulas.

Each instance is the variable-disjoint conjunction of K source formulas
drawn from *different* train families. Tests whether a solver detects
that the matrix has K connected components and solves them
independently (≈ sum of component times) rather than as one entangled
problem.

Expected: SAT iff every component is SAT; UNSAT if any component is
UNSAT (Skolem functions concatenate per-component).
"""

from __future__ import annotations

import gzip
import json
import random
from pathlib import Path

import click

from core import dqdimacs
from core.compose import conjoin

ROOT = Path(__file__).resolve().parents[3]

# (path-relative-to-ROOT, expected, family-tag)
# Chosen to span structurally distinct families with known results.
SOURCES: list[tuple[str, str, str]] = [
    # SAT
    ("benchmarks/train/peano/instances/peano_add_n8.dqdimacs.gz", "sat", "peano"),
    ("benchmarks/train/peano/instances/peano_mul_n6.dqdimacs.gz", "sat", "peano"),
    (
        "benchmarks/train/synthesis_invertibility/instances/add_zero_n16.dqdimacs.gz",
        "sat",
        "syn_inv",
    ),
    (
        "benchmarks/train/synthesis_invertibility/instances/xor_const_n16.dqdimacs.gz",
        "sat",
        "syn_inv",
    ),
    ("benchmarks/train/random_bv/under/under_w2_s0000.dqdimacs.gz", "unknown", "random_bv"),
    (
        "benchmarks/train/synthesis_invertibility/instances/and_x_n20.dqdimacs.gz",
        "sat",
        "syn_inv",
    ),
    # UNSAT
    (
        "benchmarks/train/synthesis_invertibility/instances/or_zero_n16.dqdimacs.gz",
        "unsat",
        "syn_inv",
    ),
    (
        "benchmarks/train/synthesis_invertibility/instances/shl_x_n24.dqdimacs.gz",
        "unsat",
        "syn_inv",
    ),
    ("benchmarks/train/random_bv/over/over_w2_s2000.dqdimacs.gz", "unknown", "random_bv"),
    ("benchmarks/train/bmc_circuits/unrolled/mutex/mutex_n4_k008.dqdimacs.gz", "unsat", "bmc"),
    (
        "benchmarks/train/collatz/unrolled/collatz_unrolled_shift_n16_k08.dqdimacs.gz",
        "unknown",
        "collatz",
    ),
    ("benchmarks/train/random_qbf/2qbf/2qbf_s00000.qdimacs", "unknown", "random_qbf"),
]


def _load_sources() -> list[tuple[object, str, str, str]]:
    out = []
    for rel, exp, fam in SOURCES:
        p = ROOT / rel
        if not p.exists():
            raise FileNotFoundError(f"source missing: {rel}")
        out.append((dqdimacs.load(p), exp, fam, p.name))
    return out


def _expected(exps: list[str]) -> str:
    if "unsat" in exps:
        return "unsat"
    if all(e == "sat" for e in exps):
        return "sat"
    return "unknown"


@click.command()
@click.option("--out", type=click.Path(), default="benchmarks/train/conjunction/instances")
@click.option("--seed", default=7001, type=int)
@click.option("--total", default=50, type=int)
def main(out: str, seed: int, total: int) -> None:
    outdir = Path(out)
    outdir.mkdir(parents=True, exist_ok=True)
    srcs = _load_sources()
    sat_only = [s for s in srcs if s[1] == "sat"]
    rnd = random.Random(seed)
    ks = [2, 3, 5, 8]
    per_k = {k: total // len(ks) for k in ks}
    per_k[ks[-1]] += total - sum(per_k.values())
    manifest = []
    idx = 0
    for k, n in per_k.items():
        for j in range(n):
            # Roughly a third of each K-bucket is all-SAT.
            pool = sat_only if j < (n + 2) // 3 else srcs
            picks = rnd.sample(pool, k=min(k, len(pool)))
            while len(picks) < k:
                picks.append(rnd.choice(pool))
            fams = sorted({p[2] for p in picks})
            exp = _expected([p[1] for p in picks])
            stem = f"conj_k{k}_s{seed:05d}_{idx:03d}"
            comments = (
                f"conjunction/generate.py K={k} seed={seed} idx={idx}",
                f"components={','.join(p[3] for p in picks)}",
            )
            g = conjoin([p[0] for p in picks], comments=comments)
            with gzip.open(outdir / f"{stem}.dqdimacs.gz", "wt") as fp:
                fp.write(dqdimacs.dumps(g))
            manifest.append(
                {
                    "path": f"{stem}.dqdimacs.gz",
                    "expected": exp,
                    "tags": ["conjunction", f"k{k}", *fams],
                    "params": {
                        "K": k,
                        "seed": seed,
                        "idx": idx,
                        "components": [p[3] for p in picks],
                    },
                }
            )
            idx += 1
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    sat = sum(1 for m in manifest if m["expected"] == "sat")
    unsat = sum(1 for m in manifest if m["expected"] == "unsat")
    print(
        f"wrote {len(manifest)} instances ({sat} sat / {unsat} unsat / "
        f"{len(manifest) - sat - unsat} unknown) to {outdir}/"
    )


if __name__ == "__main__":
    main()
