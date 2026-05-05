"""Inductive-invariant search → DQBF.

Given a sequential AIGER circuit (inputs I, latches L with next/reset,
combinational gates, one bad output), build a DQBF whose Skolem witness
is an **inductive invariant** `Inv : 2^|L| → bool` proving bad
unreachable. SAT ⇒ property holds (safety proven); UNSAT ⇒ no Boolean
invariant of the state exists (property is violated, since Inv = "set
of reachable states" would otherwise work).

This is the dual of `tools.bmc2dqbf.encode` (which searches for a
violating trace). The IC3/PDR view (Bradley'11; Een–Mishchenko–Brayton
FMCAD'11) is that an inductive invariant satisfies:

    (init)    I(s)                     → Inv(s)
    (cons)    Inv(s) ∧ T(s, i, s')     → Inv(s')
    (safe)    Inv(s)                   → ¬bad(s, i)

We encode `Inv` as a single existential bit `inv` with `dep = {s}`. To
apply the *same* function at the successor state we introduce a second
existential `inv'` with `dep = {s'}` and force `inv ≡ inv'` whenever
`s = s'` — the consistency-clause trick from `encode_succinct` for
tying two Skolem functions over isomorphic dependency sets.

    universals    s[0..L), i[0..I), s'[0..L)
    existentials  inv(s), inv'(s'), gate Tseitin g_k(s, i),
                  EQ/TRANS auxiliaries(s, i, s')
    clauses
      (gates)        g_k ↔ a_k ∧ b_k
      (consist)      EQ ↔ ⋀_j (s_j ↔ s'_j);  EQ → (inv ↔ inv')
      (init)         (⋀_j s_j = reset_j) → inv
      (safe)         inv → ¬bad
      (cons)         TRANS ↔ ⋀_j (s'_j ↔ next_j);  inv ∧ TRANS → inv'

The two dep-sets {s} and {s'} are incomparable, so the result is
genuine DQBF (not a QBF prefix).
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


def encode_indinv(circ: SeqAig, source: str = "<memory>") -> Formula:
    if not circ.latches:
        raise ValueError("encode_indinv: circuit has no state (no latches)")
    universals: list[int] = []
    deps: dict[int, frozenset[int]] = {}
    clauses: list[list[int]] = []
    nxt_id = 1

    def fu() -> int:
        nonlocal nxt_id
        v = nxt_id
        nxt_id += 1
        universals.append(v)
        return v

    def fe(d: frozenset[int]) -> int:
        nonlocal nxt_id
        v = nxt_id
        nxt_id += 1
        deps[v] = d
        return v

    def t_and(out: int, a: int, b: int) -> None:
        clauses.extend(([-out, a], [-out, b], [out, -a, -b]))

    def t_iff(out: int, a: int, b: int) -> None:
        clauses.extend(([-out, -a, b], [-out, a, -b], [out, a, b], [out, -a, -b]))

    def big_and(ins: list[int], d: frozenset[int]) -> int:
        out = fe(d)
        for x in ins:
            clauses.append([-out, x])
        clauses.append([out] + [-x for x in ins])
        return out

    s = [fu() for _ in circ.latches]
    i = [fu() for _ in circ.inputs]
    sp = [fu() for _ in circ.latches]
    ds, dsp, dsi = frozenset(s), frozenset(sp), frozenset(s + i)
    dall = ds | dsp | frozenset(i)
    EMPTY: frozenset[int] = frozenset()

    TRUE = fe(EMPTY)
    clauses.append([TRUE])

    inv = fe(ds)
    invp = fe(dsp)

    # current combinational frame: inputs/latches → universals; gates → ∃ Tseitin
    cur: dict[int, int] = {}
    for ai, iv in zip(circ.inputs, i, strict=True):
        cur[ai] = iv
    for lat, sv in zip(circ.latches, s, strict=True):
        cur[lat.lit] = sv
    for g, a, b in circ.gates:
        gv = fe(dsi)
        cur[g] = gv
        t_and(gv, _map_lit(a, cur, TRUE), _map_lit(b, cur, TRUE))

    bad = _map_lit(circ.bad, cur, TRUE)
    nxt = [_map_lit(lat.next, cur, TRUE) for lat in circ.latches]

    # consistency: (s == s') → (inv ↔ inv')
    eq_bits = []
    for sj, spj in zip(s, sp, strict=True):
        e = fe(ds | dsp)
        t_iff(e, sj, spj)
        eq_bits.append(e)
    EQ = big_and(eq_bits, ds | dsp)
    clauses.extend(([-EQ, -inv, invp], [-EQ, inv, -invp]))

    # init: (⋀ s_j = reset_j) → inv
    not_init = [s[j] if lat.reset == 0 else -s[j] for j, lat in enumerate(circ.latches)]
    clauses.append(not_init + [inv])

    # safe: inv → ¬bad
    clauses.append([-inv, -bad])

    # cons: inv ∧ (⋀ s'_j ↔ next_j) → inv'
    tr_bits = []
    for spj, nj in zip(sp, nxt, strict=True):
        e = fe(dall)
        t_iff(e, spj, nj)
        tr_bits.append(e)
    TRANS = big_and(tr_bits, dall)
    clauses.append([-inv, -TRANS, invp])

    comments = (
        f"hwmc2dqbf_indinv source={source}",
        f"circuit: I={len(circ.inputs)} L={len(circ.latches)} A={len(circ.gates)}",
        "semantics: SAT = inductive invariant exists = property HOLDS",
    )
    return make_formula(universals, deps, clauses, comments)
