"""Plain bounded model checking → (DQ)DIMACS.

No black boxes. Two encodings:

`encode` — **unrolled**. One copy of every input/latch/gate per step;
O(k·|circuit|) variables. Input quantification:

- `safe=False` (reachability, default): inputs are **existential** —
  TRUE iff *some* input trace makes bad hold at *some* step ≤ k. This
  is the standard BMC question abc/avy answer; the result is
  propositional SAT.
- `safe=True` (bounded safety): inputs are **universal** — TRUE iff
  *every* input trace avoids bad through step k. This is ∀∃-QBF.

`encode_succinct` — **universal step counter**. Universals are the
log₂(k+1) bits of a step index `t` (and a copy `t'`); each
input/latch/gate is a *single* existential function of `t`. The
transition relation is asserted once over (t, t+1) via a ripple
incrementer. Size O(|circuit| + log k). The result is genuine DQBF
(the two index copies have incomparable dep sets). Semantics:
∃-input-trace reachability — equisatisfiable with `encode(safe=False)`
but exponentially smaller for deep bounds.
"""

from __future__ import annotations

import math

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


# --- succinct (universal step-counter) encoding ---------------------------


def _leq_const_clauses(bits: list[int], k: int) -> list[list[int]]:
    """Clauses asserting (unsigned LSB-first `bits`) ≤ k.

    For each value v in (k, 2^len(bits)) emit one blocking clause. There
    are at most 2^m - k - 1 ≤ k such clauses, each of length m=len(bits);
    with m = ⌈log₂(k+1)⌉ this is ≤ k literals total — still tiny next to
    the O(k·|circuit|) clauses of the unrolled encoding.
    """
    m = len(bits)
    out: list[list[int]] = []
    for v in range(k + 1, 1 << m):
        out.append([-(bits[i] if (v >> i) & 1 else -bits[i]) for i in range(m)])
    return out


def encode_succinct(
    circ: SeqAig,
    k: int,
    safe: bool = False,
    source: str = "<memory>",
) -> Formula:
    """Succinct BMC: latches are ∃-functions of a universal step index.

    Universals: t[0..m), t'[0..m) with m = ⌈log₂(k+1)⌉.
    Existentials (deps shown):
      in_j(t), l_j(t), g_j(t)  — current frame, deps={t}
      l'_j(t')                 — latch copy, deps={t'}
      T[0..m)                  — target step (safe=False only), deps=∅
      Tseitin auxiliaries for EQ/STEP/incrementer/goal, deps={t}∪{t'}

    Clauses (each O(|circuit|) or O(m), independent of k):
      gate Tseitin on the current frame
      consistency:  (t == t')  → l_j == l'_j         [same function]
      init:         (t == 0)   → l_j == reset_j
      transition:   (t' == t+1)→ l'_j == next_j(cur) [incrementer, once]
      bound:        T ≤ k      (safe=False) / t ≤ k guard (safe=True)
      goal:         (t == T) → bad@cur   |   (t ≤ k) → ¬bad@cur

    `safe=True` here is ∃-input safety (∃ trace ∀t≤k ¬bad), *not* the
    ∀-input safety of `encode(safe=True)` — universal *functions* are
    not expressible in DQBF. Use safe=False for cross-checking against
    abc-bmc / `encode`.
    """
    if k < 0:
        raise ValueError("k must be ≥ 0")
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

    def tseitin_and(out: int, a: int, b: int) -> None:
        clauses.extend(([-out, a], [-out, b], [out, -a, -b]))

    def tseitin_iff(out: int, a: int, b: int) -> None:
        # out ↔ (a ↔ b)
        clauses.extend(([-out, -a, b], [-out, a, -b], [out, a, b], [out, -a, -b]))

    def big_and(ins: list[int], d: frozenset[int]) -> int:
        out = fe(d)
        for x in ins:
            clauses.append([-out, x])
        clauses.append([out] + [-x for x in ins])
        return out

    m = max(1, math.ceil(math.log2(k + 1))) if k > 0 else 1
    t = [fu() for _ in range(m)]
    tp = [fu() for _ in range(m)]
    dt = frozenset(t)
    dtp = frozenset(tp)
    dboth = dt | dtp
    EMPTY: frozenset[int] = frozenset()

    TRUE = fe(EMPTY)
    clauses.append([TRUE])

    # current frame: full combinational logic at time t
    cur: dict[int, int] = {}
    for ai in circ.inputs:
        cur[ai] = fe(dt)
    for lat in circ.latches:
        cur[lat.lit] = fe(dt)
    for g, a, b in circ.gates:
        gv = fe(dt)
        cur[g] = gv
        tseitin_and(gv, _map_lit(a, cur, TRUE), _map_lit(b, cur, TRUE))

    # next frame: latch values at time t' (same function, indexed by t')
    nxt_lat: dict[int, int] = {lat.lit: fe(dtp) for lat in circ.latches}

    # EQ ↔ (t == t')
    bit_eq = []
    for ti, tpi in zip(t, tp, strict=True):
        e = fe(dboth)
        tseitin_iff(e, ti, tpi)
        bit_eq.append(e)
    EQ = big_and(bit_eq, dboth)

    # consistency: (t==t') → cur_lat == nxt_lat
    for lat in circ.latches:
        a, b = cur[lat.lit], nxt_lat[lat.lit]
        clauses.extend(([-EQ, -a, b], [-EQ, a, -b]))

    # init: (t==0) → cur_lat == reset
    g0 = [t[i] for i in range(m)]  # ¬(t==0) disjunct = some bit set
    for lat in circ.latches:
        v = cur[lat.lit]
        clauses.append(g0 + ([v] if lat.reset == 1 else [-v]))

    # STEP ↔ (t' == t+1) ∧ ¬overflow, via ripple incrementer on t
    succ: list[int] = []
    carry = TRUE
    for i in range(m):
        s = fe(dt)
        tseitin_iff(s, t[i], -carry)  # s = t[i] ⊕ carry  ≡  t[i] ↔ ¬carry
        succ.append(s)
        c2 = fe(dt)
        tseitin_and(c2, t[i], carry)
        carry = c2
    step_bits = []
    for i in range(m):
        e = fe(dboth)
        tseitin_iff(e, tp[i], succ[i])
        step_bits.append(e)
    step_bits.append(-carry)  # no overflow (so t < 2^m - 1)
    STEP = big_and(step_bits, dboth)

    # transition: STEP → l'_j == next_j(cur)
    for lat in circ.latches:
        target = _map_lit(lat.next, cur, TRUE)
        b = nxt_lat[lat.lit]
        clauses.extend(([-STEP, -b, target], [-STEP, b, -target]))

    bad = _map_lit(circ.bad, cur, TRUE)
    if safe:
        raise NotImplementedError(
            "encode_succinct(safe=True) would mean ∃-input safety, which is "
            "not the ∀-input safety of encode(safe=True); only safe=False "
            "(reachability) is supported so the two encodings are comparable."
        )
    # ∃ target step T ≤ k with bad@T.
    T = [fe(EMPTY) for _ in range(m)]
    clauses.extend(_leq_const_clauses(T, k))
    teq = []
    for i in range(m):
        e = fe(dt)
        tseitin_iff(e, t[i], T[i])
        teq.append(e)
    EQT = big_and(teq, dt)
    clauses.append([-EQT, bad])

    comments = (
        f"bmc2dqbf.encode_succinct source={source} bound={k} safe={safe} m={m}",
        f"circuit: I={len(circ.inputs)} L={len(circ.latches)} A={len(circ.gates)}",
    )
    return make_formula(universals, deps, clauses, comments)
