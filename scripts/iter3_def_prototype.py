"""Iter-3 prototype: definability-based SAT detection for |U|>16.

Hypothesis: PEC `_complete` instances have every (live) existential
uniquely determined by dep(y) given the matrix (Padoa-definable). If so,
the formula is DQBF-SAT and the Skolem function is the unique definition.

Algorithm:
  1. Dead existentials (0 clauses) → const 0.
  2. For each live y: Padoa check — two matrix copies sharing dep(y),
     assert y_A ≠ y_B; UNSAT ⇒ y is dep-definable.
  3. If all defined → SAT.

This script validates the approach on the sampled unsolved instances.
"""
from __future__ import annotations
import time

from core.dqdimacs import load
from core.formula import Formula
from tools.verify.sat import solve_cnf


def cdcl_sat(n_vars: int, clauses: list[list[int]], assump: list[int]) -> bool | None:
    sat, _ = solve_cnf(n_vars, clauses + [[a] for a in assump])
    return sat


def padoa_all_defined(f: Formula) -> tuple[bool, list[int], float]:
    """Check every live existential is dep-definable. Returns
    (all_defined, undefined_vars, elapsed_s)."""
    n = f.n_vars
    # Two-copy clause set: A = vars 1..n, B = vars n+1..2n.
    base2: list[list[int]] = []
    for c in f.clauses:
        base2.append(list(c))
        base2.append([(n + abs(l)) * (1 if l > 0 else -1) for l in c])
    live = {abs(l) for c in f.clauses for l in c} & set(f.existentials)
    deps = {y: frozenset(f.dep(y)) for y in f.existentials}
    t0 = time.perf_counter()
    defined: set[int] = set(f.existentials) - live  # dead → trivially defined
    todo = sorted(live, key=lambda y: len(deps[y]))
    rounds = 0
    while True:
        rounds += 1
        progress = False
        still: list[int] = []
        for y in todo:
            # Share dep(y) plus already-defined z with dep(z) ⊆ dep(y).
            share = list(deps[y]) + [
                z for z in defined if deps.get(z, frozenset()) <= deps[y]
            ]
            link: list[list[int]] = []
            for d in share:
                link.append([d, -(n + d)])
                link.append([-d, n + d])
            sat = cdcl_sat(2 * n, base2 + link, [y, -(n + y)])
            if sat is False:
                defined.add(y)
                progress = True
            else:
                still.append(y)
        todo = still
        if not progress or not todo:
            break
    return len(todo) == 0, todo[:10], time.perf_counter() - t0


PATHS = [
    "benchmarks/train/pec_circuits/miter/pec_mutex_n8_k2_bb2_complete.dqdimacs.gz",
    "benchmarks/train/pec_circuits/miter/pec_alu_add_n4_k2_bb3_complete.dqdimacs.gz",
    "benchmarks/train/pec_circuits/miter/pec_fifo1_n4_k8_bb3_complete.dqdimacs.gz",
    "benchmarks/train/pec_circuits/miter/pec_mutex_n12_k2_bb3_complete.dqdimacs.gz",
    "benchmarks/train/pec_circuits/miter/pec_fifo1_n24_k2_bb2_complete.dqdimacs.gz",
    "benchmarks/train/peano/instances/peano_v2_mul_n8.dqdimacs.gz",
    "benchmarks/train/conjunction/instances/conj_k2_s07001_007.dqdimacs.gz",
]

if __name__ == "__main__":
    for p in PATHS:
        f = load(p)
        ok, undef, dt = padoa_all_defined(f)
        live = {abs(l) for c in f.clauses for l in c} & set(f.existentials)
        print(
            f"{p.split('/')[-1]:45} |U|={len(f.universals):3} "
            f"live∃={len(live):4} all_def={ok!s:5} "
            f"undef={undef[:5]} ({dt:.1f}s)"
        )
