"""Inductive-invariant search → DQBF.

Given a transition system `(state, inputs, next_state, init, trans,
bad)`, build a DQBF whose Skolem witness is an **inductive invariant**
`Inv : 2^|state| → bool` proving bad unreachable. SAT ⇒ property holds
(safety proven); UNSAT ⇒ no Boolean invariant of state exists, i.e.
bad is reachable (since the reachable-set is itself inductive).

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
    existentials  inv(s), inv'(s'), trans-aux(s, i, s'),
                  EQ/TRANS Tseitin(s, i, s')
    clauses
      (consist)      EQ ↔ ⋀_j (s_j ↔ s'_j);  EQ → (inv ↔ inv')
      (init)         I(s) → inv
      (safe)         inv → ¬bad
      (cons)         TRANS ↔ ⋀_k C_k;  inv ∧ TRANS → inv'

The two dep-sets {s} and {s'} are incomparable, so the result is
genuine DQBF (not a QBF prefix).

The encoder is frontend-agnostic: AIGER goes through
`from_seq_aig(...)`; other frontends (e.g. CBMC SSA) build a
`Transition` directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.formula import Formula, make_formula
from tools.pec2dqbf.aiger_seq import SeqAig


@dataclass(frozen=True)
class Transition:
    """A symbolic transition system in CNF.

    Variable IDs are positive ints in `1..n_vars`. The three var lists
    must be disjoint; any other ID in `1..n_vars` is an auxiliary.

    `defs`   — clauses that *define* aux vars (Tseitin gates etc.).
               These hold unconditionally; they constrain aux as
               functions of (s, i) and never restrict s' on their own.
    `trans`  — relational T(s, i, s'); used as a guard in consecution.
    `init`   — cube (conjunction of literals over `state`).
    `bad`    — literal over `state ∪ inputs ∪ aux`.

    The defs/trans split matters: `bad` may reference aux, so the gate
    definitions must be in the matrix unconditionally; but the
    next-state constraints must *not* be (s' is universal).
    """

    n_vars: int
    state: list[int]
    inputs: list[int]
    next_state: list[int]
    init: list[int]
    defs: list[list[int]]
    trans: list[list[int]]
    bad: int
    comments: tuple[str, ...] = field(default_factory=tuple)


def encode_indinv(tr: Transition, source: str = "<memory>") -> Formula:
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

    def t_iff(out: int, a: int, b: int) -> None:
        clauses.extend(([-out, -a, b], [-out, a, -b], [out, a, b], [out, -a, -b]))

    def big_and(ins: list[int], d: frozenset[int]) -> int:
        if len(ins) == 1:
            return ins[0]
        out = fe(d)
        for x in ins:
            clauses.append([-out, x])
        clauses.append([out] + [-x for x in ins])
        return out

    # universals: s, i, s'; aux from `trans` become existentials over (s,i,s')
    s = [fu() for _ in tr.state]
    i = [fu() for _ in tr.inputs]
    sp = [fu() for _ in tr.next_state]
    ds, dsp = frozenset(s), frozenset(sp)
    dall = ds | dsp | frozenset(i)

    remap: dict[int, int] = {}
    for old, new in zip(tr.state, s, strict=True):
        remap[old] = new
    for old, new in zip(tr.inputs, i, strict=True):
        remap[old] = new
    for old, new in zip(tr.next_state, sp, strict=True):
        remap[old] = new
    fixed = set(tr.state) | set(tr.inputs) | set(tr.next_state)
    for v in range(1, tr.n_vars + 1):
        if v not in fixed:
            remap[v] = fe(dall)

    def r(lit: int) -> int:
        return remap[abs(lit)] if lit > 0 else -remap[-lit]

    inv = fe(ds)
    invp = fe(dsp)

    # defs: unconditional (define aux as functions of s, i)
    for c in tr.defs:
        clauses.append([r(lit) for lit in c])

    # consistency: (s == s') → (inv ↔ inv')
    eq_bits = []
    for sj, spj in zip(s, sp, strict=True):
        e = fe(ds | dsp)
        t_iff(e, sj, spj)
        eq_bits.append(e)
    EQ = big_and(eq_bits, ds | dsp)
    clauses.extend(([-EQ, -inv, invp], [-EQ, inv, -invp]))

    # init: (⋀ init-cube) → inv
    clauses.append([-r(lit) for lit in tr.init] + [inv])

    # safe: inv → ¬bad
    clauses.append([-inv, -r(tr.bad)])

    # cons: inv ∧ (⋀ trans-clauses) → inv'.  Tseitin each clause as an OR,
    # big-AND them into TRANS, then [¬inv, ¬TRANS, inv'].
    sat_bits: list[int] = []
    for c in tr.trans:
        rc = [r(lit) for lit in c]
        if len(rc) == 1:
            sat_bits.append(rc[0])
            continue
        t = fe(dall)
        for lit in rc:
            clauses.append([-lit, t])
        clauses.append([-t] + rc)
        sat_bits.append(t)
    TRANS = big_and(sat_bits, dall)
    clauses.append([-inv, -TRANS, invp])

    comments = (
        f"hwmc2dqbf_indinv source={source}",
        f"transition: |s|={len(tr.state)} |i|={len(tr.inputs)} |T|={len(tr.trans)}",
        "semantics: SAT = inductive invariant exists = property HOLDS",
        *tr.comments,
    )
    return make_formula(universals, deps, clauses, comments)


# --- AIGER frontend -------------------------------------------------------


def _map_lit(aiglit: int, alit: dict[int, int], true_var: int) -> int:
    v = aiglit & ~1
    sgn = -1 if aiglit & 1 else 1
    if v == 0:
        return sgn * (-true_var)
    return sgn * alit[v]


def from_seq_aig(circ: SeqAig) -> Transition:
    """Build a `Transition` from a sequential AIGER circuit.

    state = latches, inputs = primary inputs, next_state = fresh copies;
    `trans` is gate Tseitin + per-latch `s'_j ↔ next_j(s, i)`.
    """
    if not circ.latches:
        raise ValueError("from_seq_aig: circuit has no state")
    nxt = 1
    state: list[int] = []
    inputs: list[int] = []
    next_state: list[int] = []
    cur: dict[int, int] = {}
    trans: list[list[int]] = []

    def fresh() -> int:
        nonlocal nxt
        v = nxt
        nxt += 1
        return v

    for lat in circ.latches:
        v = fresh()
        state.append(v)
        cur[lat.lit] = v
    for ai in circ.inputs:
        v = fresh()
        inputs.append(v)
        cur[ai] = v
    for _ in circ.latches:
        next_state.append(fresh())
    TRUE = fresh()
    defs: list[list[int]] = [[TRUE]]
    for g, a, b in circ.gates:
        gv = fresh()
        cur[g] = gv
        ga, gb = _map_lit(a, cur, TRUE), _map_lit(b, cur, TRUE)
        defs += [[-gv, ga], [-gv, gb], [gv, -ga, -gb]]
    for lat, spj in zip(circ.latches, next_state, strict=True):
        n = _map_lit(lat.next, cur, TRUE)
        trans += [[-spj, n], [spj, -n]]

    init = [-state[j] if lat.reset == 0 else state[j] for j, lat in enumerate(circ.latches)]
    bad = _map_lit(circ.bad, cur, TRUE)
    return Transition(
        n_vars=nxt - 1,
        state=state,
        inputs=inputs,
        next_state=next_state,
        init=init,
        defs=defs,
        trans=trans,
        bad=bad,
        comments=(f"aiger: I={len(circ.inputs)} L={len(circ.latches)} A={len(circ.gates)}",),
    )


def encode_indinv_aig(circ: SeqAig, source: str = "<memory>") -> Formula:
    """Convenience: `encode_indinv(from_seq_aig(circ))`."""
    return encode_indinv(from_seq_aig(circ), source=source)
