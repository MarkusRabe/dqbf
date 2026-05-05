"""Iter-3 prototype B: dependency-aware semantic gate elimination.

For each existential y, take its clause-neighbourhood as candidate
support I. If |I| small, enumerate 2^|I| and check whether the y-clauses
force y in every row. If so, y is a gate over I — eliminate it (record
definition, resolve away). Repeat to fixpoint. Report how much of |E|
this kills and what the residual |U|,|E| look like.
"""
from __future__ import annotations
import time

from core.dqdimacs import load
from core.formula import Formula


def neighbourhood(clauses: list[frozenset[int]], y: int) -> tuple[list[frozenset[int]], set[int]]:
    on_y = [c for c in clauses if y in c or -y in c]
    supp = {abs(l) for c in on_y for l in c} - {y}
    return on_y, supp


def is_gate(on_y: list[frozenset[int]], y: int, supp: list[int]) -> list[int] | None:
    """If on_y forces y for every assignment to supp, return the truth
    table (list of 0/1 indexed by supp-row). Else None."""
    if len(supp) > 6:
        return None
    n = len(supp)
    table: list[int] = []
    for r in range(1 << n):
        a = {supp[i]: 1 if (r >> i) & 1 else -1 for i in range(n)}
        forced: int | None = None
        for c in on_y:
            un = []
            sat = False
            for l in c:
                v = abs(l)
                if v == y:
                    un.append(l)
                elif (a[v] > 0) == (l > 0):
                    sat = True
                    break
            if sat:
                continue
            if not un:
                return None  # conflict in supp alone → not a clean gate
            # all non-y lits false → y forced to un[0]'s polarity
            want = 1 if un[0] > 0 else 0
            if forced is None:
                forced = want
            elif forced != want:
                return None  # contradictory forcing
        if forced is None:
            return None  # not forced in this row
        table.append(forced)
    return table


def eliminate_gates(f: Formula) -> tuple[dict[int, tuple[list[int], list[int]]], set[int], list[frozenset[int]]]:
    """Returns (defs, residual_existentials, residual_clauses).
    defs[y] = (support_vars, truth_table)."""
    clauses = list(f.clauses)
    exs = set(f.existentials)
    deps = {y: frozenset(f.dep(y)) for y in exs}
    eff_dep = dict(deps)  # effective dep after elimination
    defs: dict[int, tuple[list[int], list[int]]] = {}
    changed = True
    while changed:
        changed = False
        for y in sorted(exs - set(defs)):
            on_y, supp = neighbourhood(clauses, y)
            if not on_y:
                defs[y] = ([], [0])  # dead → const 0
                changed = True
                continue
            # dep-aware: support vars must each be in dep(y) (universals)
            # or be already-defined existentials with eff_dep ⊆ dep(y)
            ok = True
            for s in supp:
                if s in f.universals:
                    if s not in deps[y]:
                        ok = False
                        break
                elif s in defs:
                    if not eff_dep[s] <= deps[y]:
                        ok = False
                        break
                else:
                    ok = False
                    break
            if not ok:
                continue
            sl = sorted(supp)
            tbl = is_gate(on_y, y, sl)
            if tbl is None:
                continue
            defs[y] = (sl, tbl)
            eff_dep[y] = frozenset().union(*(eff_dep.get(s, frozenset({s})) & set(f.universals) | ({s} if s in f.universals else eff_dep[s]) for s in sl)) if sl else frozenset()
            # Resolve y away: drop on_y, and in every other clause
            # containing y/-y... actually for prototype, just drop on_y
            # and substitute later. Keep clauses but mark y as defined.
            # For residual-size accounting, remove on_y.
            clauses = [c for c in clauses if y not in c and -y not in c]
            changed = True
    residual_ex = exs - set(defs)
    return defs, residual_ex, clauses


PATHS = [
    "benchmarks/train/pec_circuits/instances/pec_mutex_n8_k2_bb2_complete.dqdimacs.gz",
    "benchmarks/train/pec_circuits/instances/pec_alu_add_n4_k2_bb3_complete.dqdimacs.gz",
    "benchmarks/train/pec_circuits/instances/pec_fifo1_n4_k8_bb3_complete.dqdimacs.gz",
    "benchmarks/train/pec_circuits/instances/pec_mutex_n12_k2_bb3_complete.dqdimacs.gz",
    "benchmarks/train/pec_circuits/instances/pec_fifo1_n24_k2_bb2_complete.dqdimacs.gz",
    "benchmarks/train/peano/instances/peano_v2_mul_n8.dqdimacs.gz",
    "benchmarks/train/conjunction/instances/conj_k2_s07001_007.dqdimacs.gz",
]

if __name__ == "__main__":
    for p in PATHS:
        f = load(p)
        t0 = time.perf_counter()
        defs, residual, rclauses = eliminate_gates(f)
        dt = time.perf_counter() - t0
        max_rdep = max((len(f.dep(y)) for y in residual), default=0)
        print(
            f"{p.split('/')[-1]:45} |E|={len(f.existentials):4}→{len(residual):3} "
            f"|C|={len(f.clauses):5}→{len(rclauses):4} "
            f"max|dep(residual)|={max_rdep:3} ({dt:.2f}s)"
        )
        if residual and len(residual) <= 12:
            for y in sorted(residual):
                ny = sum(1 for c in rclauses if y in c or -y in c)
                print(f"    residual y={y:4} |dep|={len(f.dep(y)):3} #cls={ny}")
