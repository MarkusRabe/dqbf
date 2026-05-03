"""Plain bounded model checking → (DQ)DIMACS.

No black boxes. Per-step primary inputs are **universal**; latches and
gate outputs at step `t` are existential with dependency set = every
input universal at steps `0..t`. That is a linearly nested prefix, so
the result is QBF (a DQDIMACS subset) and any QBF solver decides it.

The formula is TRUE iff, for **every** input trace of length `k+1`, the
circuit (started from its reset state) reaches the bad output at step
`k`. With `safe=True` the goal is `⋀_t ¬bad_t` instead, i.e. TRUE iff
bad is unreachable within `k` steps under every input trace.
"""

from __future__ import annotations

from core.formula import Formula, make_formula
from tools.pec2dqbf.aiger_seq import SeqAig


def _map_lit(aiglit: int, alit: dict[int, int], true_var: int) -> int:
    v = aiglit & ~1
    sgn = -1 if aiglit & 1 else 1
    if v == 0:
        return sgn * (-true_var)
    return sgn * alit[v]


def encode(circ: SeqAig, k: int, safe: bool = False, source: str = "<memory>") -> Formula:
    universals: list[int] = []
    deps: dict[int, frozenset[int]] = {}
    clauses: list[list[int]] = []
    nxt = 1

    def fresh_u() -> int:
        nonlocal nxt
        v = nxt
        nxt += 1
        universals.append(v)
        return v

    def fresh_e(d: frozenset[int]) -> int:
        nonlocal nxt
        v = nxt
        nxt += 1
        deps[v] = d
        return v

    TRUE = fresh_e(frozenset())
    clauses.append([TRUE])

    step: list[dict[int, int]] = []
    for _t in range(k + 1):
        alit: dict[int, int] = {}
        prior_u = frozenset(universals)
        for ai in circ.inputs:
            alit[ai] = fresh_u()
        all_u = frozenset(universals)
        for lat in circ.latches:
            alit[lat.lit] = fresh_e(prior_u)
        for g, a, b in circ.gates:
            gv = fresh_e(all_u)
            alit[g] = gv
            ga = _map_lit(a, alit, TRUE)
            gb = _map_lit(b, alit, TRUE)
            clauses += [[-gv, ga], [-gv, gb], [gv, -ga, -gb]]
        step.append(alit)

    for lat in circ.latches:
        v0 = step[0][lat.lit]
        clauses.append([v0] if lat.reset == 1 else [-v0])

    for t in range(k):
        cur, nxt_ = step[t], step[t + 1]
        for lat in circ.latches:
            tgt = _map_lit(lat.next, cur, TRUE)
            clauses += [[-nxt_[lat.lit], tgt], [nxt_[lat.lit], -tgt]]

    bad_at = [_map_lit(circ.bad, step[t], TRUE) for t in range(k + 1)]
    if safe:
        for b in bad_at:
            clauses.append([-b])
    else:
        clauses.append([bad_at[k]])

    comments = (
        f"bmc2dqbf source={source} bound={k} safe={safe}",
        f"circuit: I={len(circ.inputs)} L={len(circ.latches)} A={len(circ.gates)}",
    )
    return make_formula(universals, deps, clauses, comments)
