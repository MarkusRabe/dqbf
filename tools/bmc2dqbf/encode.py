"""Plain bounded model checking → (DQ)DIMACS.

No black boxes. Input quantification depends on the question:

- `safe=False` (reachability, default): inputs are **existential** —
  TRUE iff *some* input trace makes bad hold at *some* step ≤ k. This
  is the standard BMC question abc/avy answer; the result is
  propositional SAT.
- `safe=True` (bounded safety): inputs are **universal** — TRUE iff
  *every* input trace avoids bad through step k. This is ∀∃-QBF.

`forall_inputs` overrides the default if you want the non-standard
combination.
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


def encode(
    circ: SeqAig,
    k: int,
    safe: bool = False,
    forall_inputs: bool | None = None,
    source: str = "<memory>",
) -> Formula:
    if forall_inputs is None:
        forall_inputs = safe
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
            alit[ai] = fresh_u() if forall_inputs else fresh_e(prior_u)
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
        clauses.append(list(bad_at))

    comments = (
        f"bmc2dqbf source={source} bound={k} safe={safe} forall_inputs={forall_inputs}",
        f"circuit: I={len(circ.inputs)} L={len(circ.latches)} A={len(circ.gates)}",
    )
    return make_formula(universals, deps, clauses, comments)
