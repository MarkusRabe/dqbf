"""Phase-3/4/6 experiments: measure how much one conflict actually teaches.

The point of the experiment, derived from first principles:

A conflict at decision level `d` exposes a sub-CNF `K` (the cone) that
is UNSAT under the trail. The set of *valid learned clauses* is exactly
the set of cone-implicates falsified by the trail. The 1-UIP clause is
one of them. The questions:

1. How many distinct, mutually-non-subsuming clauses are in that set?
   (Phase 3 — counted by bounded cut enumeration; verified for small
   cones by exact prime-implicate computation.)

2. Does the count depend on the *structure* of the cone (XOR, equality,
   cardinality, arithmetic, unstructured)? On the *size* of the cone?
   (Phase 3, swept across instance classes and sizes.)

3. Is there a representation smaller than the full set that the CDCL
   machinery can *propagate*? (Phase 6: multi-learn k clauses; ext-learn
   = Tseitin the cone gates; xor-learn = parity constraints. Measure
   propagations-per-learned-clause and conflicts-to-solve.)

The experiment is parameterizable: add a generator to ``generators.py``
and a sweep entry to ``SWEEPS`` below.
"""

from __future__ import annotations

import csv
import statistics
import sys
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from cdcl import Cdcl, Clause, ConflictCone, Lit, Stats, solve_cnf
from conflict_analysis import (
    ExtLearn,
    Instrument,
    LearnLog,
    MultiLearn,
    XorLearn,
    classify_cone,
)
from generators import (
    adder_miter,
    at_most_k_vs_at_least,
    equality_chain,
    equality_grid,
    multiplier_miter,
    parity_tree,
    php,
    random_3sat,
    tseitin_xor_chain,
)


# ───────────────────────── sweep definitions ─────────────────────────

# Each sweep is (class, list of (name, n_vars, clauses)). Sizes are tuned
# so the *Python* CDCL takes < ~30 s with the instrument attached.
SWEEPS: dict[str, list[tuple[str, int, list[Clause]]]] = {
    "xor_chain": [(f"n{n}", *tseitin_xor_chain(n)) for n in (4, 6, 8, 10, 12, 16, 20)],
    "parity_tree": [(f"n{n}", *parity_tree(n)) for n in (4, 6, 8, 10, 12)],
    "eq_chain": [(f"n{n}", *equality_chain(n)) for n in (8, 16, 32, 64)],
    "eq_grid": [(f"{r}x{c}", *equality_grid(r, c)) for r, c in ((3, 3), (4, 4), (5, 5), (6, 6))],
    "adder": [(f"w{w}", *adder_miter(w)) for w in (2, 3, 4, 5, 6)],
    "multiplier": [(f"w{w}", *multiplier_miter(w)) for w in (2, 3)],
    "php": [(f"n{n}", *php(n)) for n in (3, 4, 5, 6)],
    "card_seq": [(f"n{n}_k{k}", *at_most_k_vs_at_least(n, k)) for n, k in ((8, 3), (12, 4), (16, 5), (20, 6))],
    "random3sat": [
        (f"n{n}_s{s}", *random_3sat(n, seed=s))
        for n, s in ((30, 1), (40, 2), (50, 3), (40, 11), (50, 12))
    ],
}


# ───────────────────────── Phase 3: cuts per conflict ─────────────────────────


def phase3(
    classes: Iterable[str] | None = None,
    *,
    cap: int = 32,
    do_implicates: bool = True,
    max_implicate_vars: int = 13,
    max_conflicts: int = 3000,
    out_csv: str | None = "phase3.csv",
) -> dict[str, dict]:
    """Run the instrument hook and collect per-conflict statistics."""
    classes = list(classes) if classes else list(SWEEPS)
    rows: list[dict] = []
    summary: dict[str, dict] = {}

    for cls_name in classes:
        for inst_name, nv, cls in SWEEPS[cls_name]:
            ins = Instrument(cap=cap, do_implicates=do_implicates, max_implicate_vars=max_implicate_vars)
            t0 = time.time()
            r, st = solve_cnf(nv, cls, conflict_hook=ins, max_conflicts=max_conflicts)
            dt = time.time() - t0
            log = ins.log
            if not log:
                continue
            impl = [e.n_implicates for e in log if e.n_implicates is not None]
            # how often do prime implicates exceed the cap (i.e., we
            # truly cannot enumerate them as clauses)?
            impl_uncapped = [e.n_implicates for e in log if e.n_implicates is not None]
            row = {
                "class": cls_name,
                "name": inst_name,
                "n_vars": nv,
                "n_clauses": len(cls),
                "result": {True: "SAT", False: "UNSAT", None: "?"}[r],
                "conflicts": st.conflicts,
                "time_s": round(dt, 2),
                "avg_cone_size": round(statistics.mean(e.cone_size for e in log), 1),
                "avg_width": round(statistics.mean(e.width for e in log), 1),
                "avg_depth": round(statistics.mean(e.depth for e in log), 1),
                "avg_sharing": round(statistics.mean(e.sharing for e in log), 1),
                "avg_uips": round(statistics.mean(e.n_uips for e in log), 2),
                "avg_cuts": round(statistics.mean(e.n_cuts for e in log), 2),
                "avg_nonsub": round(statistics.mean(e.n_nonsubsumed for e in log), 2),
                "max_nonsub": max(e.n_nonsubsumed for e in log),
                "avg_uip_len": round(statistics.mean(e.uip_clause_len for e in log), 1),
                "avg_implicates": round(statistics.mean(impl), 1) if impl else None,
                "max_implicates": max(impl) if impl else None,
                "n_implicate_samples": len(impl),
            }
            rows.append(row)
            print(
                f"  {cls_name:>12} {inst_name:<8} "
                f"conf={row['conflicts']:>5} "
                f"cuts={row['avg_nonsub']:>5.1f}/{row['max_nonsub']:>3} "
                f"width={row['avg_width']:>4.1f} "
                f"depth={row['avg_depth']:>4.1f} "
                f"impl={row['avg_implicates'] if row['avg_implicates'] is not None else '-':>6}"
            )
        # per-class summary
        cls_rows = [r for r in rows if r["class"] == cls_name]
        if cls_rows:
            summary[cls_name] = {
                "avg_nonsub": round(statistics.mean(r["avg_nonsub"] for r in cls_rows), 2),
                "max_nonsub": max(r["max_nonsub"] for r in cls_rows),
                "avg_width": round(statistics.mean(r["avg_width"] for r in cls_rows), 1),
                "avg_depth": round(statistics.mean(r["avg_depth"] for r in cls_rows), 1),
                "avg_sharing": round(statistics.mean(r["avg_sharing"] for r in cls_rows), 1),
                "avg_implicates": round(
                    statistics.mean(
                        r["avg_implicates"] for r in cls_rows if r["avg_implicates"] is not None
                    ),
                    1,
                )
                if any(r["avg_implicates"] is not None for r in cls_rows)
                else None,
            }

    if out_csv and rows:
        with open(out_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\n→ wrote {out_csv} ({len(rows)} rows)")
    return summary


# ───────────────────────── Phase 6: learning strategies ─────────────────────────


@dataclass
class Run:
    strategy: str
    result: str
    conflicts: int
    propagations: int
    learned: int
    learned_lits: int
    n_vars_added: int
    time_s: float
    reuse_rate: float | None = None  # ext-learn only

    @property
    def props_per_learned(self) -> float:
        return self.propagations / max(1, self.learned)

    @property
    def props_per_conflict(self) -> float:
        return self.propagations / max(1, self.conflicts)


def _run_strategy(
    nv: int,
    cls: list[Clause],
    strat: str,
    *,
    max_conflicts: int = 5000,
) -> Run:
    """Run one solving strategy and collect counters."""
    extra_vars = 0
    reuse = None

    if strat == "1uip":
        hook = None
    elif strat.startswith("multi"):
        k = int(strat[5:])
        hook = MultiLearn(k)
    elif strat == "ext":
        # ext-learn needs to allocate fresh variables; pre-allocate a
        # generous pool so the CDCL's arrays are big enough.
        pool = nv + 200
        ext = ExtLearn(next_var=nv + 1, only_structured=False)
        hook = ext
    elif strat == "ext_struct":
        pool = nv + 200
        ext = ExtLearn(next_var=nv + 1, only_structured=True)
        hook = ext
    elif strat == "xor":
        pool = nv + 200
        xl = XorLearn(next_var=nv + 1)
        hook = xl
    else:
        raise ValueError(strat)

    if strat in ("ext", "ext_struct", "xor"):
        s = Cdcl(pool, conflict_hook=hook)
    else:
        s = Cdcl(nv, conflict_hook=hook)
    for c in cls:
        s.add_clause(c)
    t0 = time.time()
    r = s.solve(max_conflicts=max_conflicts)
    dt = time.time() - t0
    if strat in ("ext", "ext_struct"):
        extra_vars = hook.next_var - nv - 1  # type: ignore
        if hook.hits + hook.misses > 0:  # type: ignore
            reuse = hook.hits / (hook.hits + hook.misses)  # type: ignore
    elif strat == "xor":
        extra_vars = hook.next_var - nv - 1  # type: ignore
    return Run(
        strategy=strat,
        result={True: "SAT", False: "UNSAT", None: "?"}[r],
        conflicts=s.stats.conflicts,
        propagations=s.stats.propagations,
        learned=s.stats.learned,
        learned_lits=s.stats.learned_lits,
        n_vars_added=extra_vars,
        time_s=round(dt, 2),
        reuse_rate=round(reuse, 2) if reuse is not None else None,
    )


def phase6(
    classes: Iterable[str] | None = None,
    *,
    strategies: list[str] | None = None,
    max_conflicts: int = 5000,
    out_csv: str | None = "phase6.csv",
) -> list[dict]:
    """Compare learning strategies across instance classes."""
    classes = list(classes) if classes else list(SWEEPS)
    strategies = strategies or ["1uip", "multi2", "multi4", "multi8", "ext", "ext_struct", "xor"]
    rows: list[dict] = []

    for cls_name in classes:
        for inst_name, nv, cls in SWEEPS[cls_name]:
            base = None
            for strat in strategies:
                run = _run_strategy(nv, cls, strat, max_conflicts=max_conflicts)
                if strat == "1uip":
                    base = run
                row = {
                    "class": cls_name,
                    "name": inst_name,
                    "strategy": strat,
                    "result": run.result,
                    "conflicts": run.conflicts,
                    "props": run.propagations,
                    "learned": run.learned,
                    "vars_added": run.n_vars_added,
                    "props_per_learned": round(run.props_per_learned, 2),
                    "props_per_conflict": round(run.props_per_conflict, 2),
                    "reuse": run.reuse_rate,
                    "time_s": run.time_s,
                    "speedup_vs_1uip": (
                        round(base.conflicts / max(1, run.conflicts), 2)
                        if base and base.result == run.result and run.result != "?"
                        else None
                    ),
                }
                rows.append(row)
            print(
                f"  {cls_name:>12} {inst_name:<10} "
                + " ".join(
                    f"{r['strategy']}={r['conflicts']:>5}"
                    for r in rows
                    if r["class"] == cls_name and r["name"] == inst_name
                )
            )

    if out_csv and rows:
        with open(out_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\n→ wrote {out_csv} ({len(rows)} rows)")
    return rows


# ───────────────────────── CLI ─────────────────────────


def main() -> None:
    args = sys.argv[1:]
    classes = None
    if args and args[0] != "all":
        classes = args[0].split(",")
    print("=== Phase 3: cuts per conflict ===")
    summary = phase3(classes)
    print("\n=== Phase 3 class summary ===")
    print(f"{'class':>12}  {'cuts':>6}  {'max':>4}  {'width':>6}  {'depth':>6}  {'share':>6}  {'impl':>6}")
    for c, s in summary.items():
        print(
            f"{c:>12}  {s['avg_nonsub']:>6.1f}  {s['max_nonsub']:>4}  "
            f"{s['avg_width']:>6.1f}  {s['avg_depth']:>6.1f}  {s['avg_sharing']:>6.1f}  "
            f"{s['avg_implicates'] if s['avg_implicates'] is not None else '-':>6}"
        )
    print("\n=== Phase 6: learning strategies ===")
    phase6(classes)


if __name__ == "__main__":
    main()
