"""LTL bounded synthesis → DQBF (bounded-unrolling lasso encoding).

The correct encoding (Faymonville-Finkbeiner-Tentrup, arXiv:1803.09566
§4) is per-transition over the **universal co-Büchi automaton of ¬φ**:
∃δ,λ,θ. ∀s,s',q,q',i. (consistency ∧ θ-monotone on rejecting q). The
ranking annotation θ is what makes the local check sufficient for all
ω-words. That requires an LTL→UCW translator (`spot`, `ltl3ba`).

This module ships an **automaton-free fallback** that unrolls one
∀-quantified input trace of length k with a lasso loop. **It is sound
only for the safety fragment** (G, X, R — no F, U, W): for liveness
specs the system can choose state s_k = s_{k-1} so the loop is a
single step, making any GF antecedent trivially false. `encode()`
therefore raises `EncodingNotSound` on liveness specs unless
`unsafe_liveness=True` is passed.

Variables (allocated so the prefix is QBF-nested):
  ∀  i_{t,j}   t∈[0,k), j∈|I|   — environment input at step t
  ∃  o_{t,j}   t∈[0,k), j∈|O|   deps = i_{0..t}        (Mealy output)
  ∃  s_{t,j}   t∈[1,k], j∈[n]   deps = i_{0..t-1}      (system state)
  ∃  L_t       t∈[0,k)          deps = i_{0..k-1}      (loop selector)
  ∃  Tseitin auxiliaries        deps = i_{0..k-1}

For safety specs:
  SAT   ⇔  REALIZABLE with ≤ 2^n states (sound and complete for the
           fragment, since safety violations have a finite bad prefix).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.formula import Formula, make_formula
from tools.ltlsynth2dqbf.ltl import Node, atoms_of, has_liveness
from tools.ltlsynth2dqbf.ltl import parse as parse_ltl
from tools.ltlsynth2dqbf.tlsf import TlsfSpec
from tools.ltlsynth2dqbf.tlsf import parse as parse_tlsf


class EncodingNotSound(ValueError):
    pass


@dataclass
class _Enc:
    universals: list[int] = field(default_factory=list)
    deps: dict[int, frozenset[int]] = field(default_factory=dict)
    clauses: list[list[int]] = field(default_factory=list)
    nxt: int = 1
    TRUE: int = 0  # set after universals

    def fresh_u(self) -> int:
        v = self.nxt
        self.nxt += 1
        self.universals.append(v)
        return v

    def fresh_e(self, d: frozenset[int]) -> int:
        v = self.nxt
        self.nxt += 1
        self.deps[v] = d
        return v

    def cl(self, *lits: int) -> None:
        self.clauses.append(list(lits))

    def mk_and(self, a: int, b: int, d: frozenset[int]) -> int:
        if a == self.TRUE:
            return b
        if b == self.TRUE:
            return a
        if a == -self.TRUE or b == -self.TRUE:
            return -self.TRUE
        g = self.fresh_e(d)
        self.cl(-g, a)
        self.cl(-g, b)
        self.cl(g, -a, -b)
        return g

    def mk_or(self, a: int, b: int, d: frozenset[int]) -> int:
        if a == -self.TRUE:
            return b
        if b == -self.TRUE:
            return a
        if a == self.TRUE or b == self.TRUE:
            return self.TRUE
        g = self.fresh_e(d)
        self.cl(-g, a, b)
        self.cl(g, -a)
        self.cl(g, -b)
        return g

    def mk_iff(self, a: int, b: int, d: frozenset[int]) -> int:
        g = self.fresh_e(d)
        self.cl(-g, -a, b)
        self.cl(-g, a, -b)
        self.cl(g, a, b)
        self.cl(g, -a, -b)
        return g

    def big_and(self, lits: list[int], d: frozenset[int]) -> int:
        g = self.TRUE
        for x in lits:
            g = self.mk_and(g, x, d)
        return g

    def big_or(self, lits: list[int], d: frozenset[int]) -> int:
        g = -self.TRUE
        for x in lits:
            g = self.mk_or(g, x, d)
        return g


def encode_tlsf(text: str, n_states: int, k: int, source: str = "<memory>") -> Formula:
    spec = parse_tlsf(text)
    phi = parse_ltl(spec.ltl_formula())
    return encode(spec.inputs, spec.outputs, phi, n_states=n_states, k=k, source=source)


def encode(
    inputs: list[str],
    outputs: list[str],
    phi: Node,
    n_states: int,
    k: int,
    source: str = "<memory>",
    unsafe_liveness: bool = False,
) -> Formula:
    if k < 1:
        raise ValueError("k must be ≥ 1")
    if has_liveness(phi) and not unsafe_liveness:
        raise EncodingNotSound(
            "spec contains F/U/W; the unroll-lasso encoding is unsound for "
            "liveness (system can pick a degenerate loop). Use spot-based "
            "co-Büchi encoding or pass unsafe_liveness=True for experiments."
        )
    used = atoms_of(phi)
    unknown = used - set(inputs) - set(outputs)
    if unknown:
        raise ValueError(f"LTL atoms not declared as input/output: {sorted(unknown)}")
    e = _Enc()

    # ∀ loop selector (one bit per position; the assertion is guarded on
    # at-most-one ∧ valid-back-edge, so the spec must hold for *every*
    # consistent lasso the environment can name).
    L = [e.fresh_u() for _ in range(k)]

    i_var: list[dict[str, int]] = []
    deps_upto: list[frozenset[int]] = []
    acc: list[int] = []
    for _t in range(k):
        row = {nm: e.fresh_u() for nm in inputs}
        i_var.append(row)
        acc = acc + list(row.values())
        deps_upto.append(frozenset(acc))
    full = frozenset(e.universals)

    e.TRUE = e.fresh_e(frozenset())
    e.cl(e.TRUE)

    o_var: list[dict[str, int]] = []
    for t in range(k):
        o_var.append({nm: e.fresh_e(deps_upto[t]) for nm in outputs})

    s_var: list[list[int]] = [[-e.TRUE for _ in range(n_states)]]
    for t in range(1, k + 1):
        s_var.append([e.fresh_e(deps_upto[t - 1]) for _ in range(n_states)])

    # Functional consistency (Ackermann congruence on δ, λ).
    for t1 in range(k):
        for t2 in range(t1 + 1, k):
            same_si: list[int] = []
            for j in range(n_states):
                same_si.append(e.mk_iff(s_var[t1][j], s_var[t2][j], full))
            for nm in inputs:
                same_si.append(e.mk_iff(i_var[t1][nm], i_var[t2][nm], full))
            same = e.big_and(same_si, full)
            for j in range(n_states):
                eqn = e.mk_iff(s_var[t1 + 1][j], s_var[t2 + 1][j], full)
                e.cl(-same, eqn)
            for nm in outputs:
                eqo = e.mk_iff(o_var[t1][nm], o_var[t2][nm], full)
                e.cl(-same, eqo)

    # Loop validity guard (universal L is "valid" iff one-hot ∧ s_k = s_{L}).
    state_eq: list[int] = []
    for t in range(k):
        bits = [e.mk_iff(s_var[k][j], s_var[t][j], full) for j in range(n_states)]
        state_eq.append(e.big_and(bits, full))
    # At least one back-edge must exist (otherwise the system could avoid
    # every lasso when 2^n_states > k and trivially satisfy the guard).
    e.cl(*state_eq) if state_eq else None
    one_hot = e.big_or(L, full)
    for a in range(k):
        for b in range(a + 1, k):
            one_hot = e.mk_and(one_hot, e.mk_or(-L[a], -L[b], full), full)
    eq_parts = [e.mk_or(-L[t], state_eq[t], full) for t in range(k)]
    valid_loop = e.mk_and(one_hot, e.big_and(eq_parts, full), full)
    inloop = e.big_or(L, full)
    in_loop_at: list[int] = []
    cur = -e.TRUE
    for t in range(k):
        cur = e.mk_or(cur, L[t], full)
        in_loop_at.append(cur)

    memo: dict[tuple[int, int], int] = {}

    def ev(n: Node, t: int) -> int:
        key = (id(n), t)
        if key in memo:
            return memo[key]
        op = n[0]
        if op == "true":
            r = e.TRUE
        elif op == "false":
            r = -e.TRUE
        elif op == "atom":
            nm = n[1]
            r = i_var[t][nm] if nm in i_var[t] else o_var[t][nm]
        elif op == "not":
            r = -ev(n[1], t)
        elif op == "and":
            r = e.mk_and(ev(n[1], t), ev(n[2], t), full)
        elif op == "or":
            r = e.mk_or(ev(n[1], t), ev(n[2], t), full)
        elif op == "impl":
            r = e.mk_or(-ev(n[1], t), ev(n[2], t), full)
        elif op == "iff":
            r = e.mk_iff(ev(n[1], t), ev(n[2], t), full)
        elif op == "X":
            if t + 1 < k:
                r = ev(n[1], t + 1)
            else:
                opts = [e.mk_and(L[j], ev(n[1], j), full) for j in range(k)]
                r = e.big_or(opts, full)
        elif op == "G":
            r = _eval_G(n[1], t)
        elif op == "F":
            r = _eval_F(n[1], t)
        elif op == "U":
            r = _eval_U(n[1], n[2], t)
        elif op == "W":
            r = e.mk_or(_eval_G(n[1], t), _eval_U(n[1], n[2], t), full)
        elif op == "R":
            r = -_eval_U(("not", n[1]), ("not", n[2]), t)
        else:
            raise ValueError(f"LTL op {op!r}")
        memo[key] = r
        return r

    def _eval_G(a: Node, t: int) -> int:
        suffix = e.big_and([ev(a, j) for j in range(t, k)], full)
        loop_part = e.big_and([e.mk_or(-in_loop_at[j], ev(a, j), full) for j in range(k)], full)
        return e.mk_and(suffix, e.mk_and(inloop, loop_part, full), full)

    def _eval_F(a: Node, t: int) -> int:
        suffix = e.big_or([ev(a, j) for j in range(t, k)], full)
        loop_part = e.big_or([e.mk_and(in_loop_at[j], ev(a, j), full) for j in range(k)], full)
        return e.mk_or(suffix, e.mk_and(inloop, loop_part, full), full)

    def _eval_U(a: Node, b: Node, t: int) -> int:
        opts: list[int] = []
        for j in range(t, k):
            pre = e.big_and([ev(a, m) for m in range(t, j)], full)
            opts.append(e.mk_and(ev(b, j), pre, full))
        a_suffix = e.big_and([ev(a, m) for m in range(t, k)], full)
        a_loop = e.big_and([e.mk_or(-in_loop_at[m], ev(a, m), full) for m in range(k)], full)
        b_loop = e.big_or([e.mk_and(in_loop_at[m], ev(b, m), full) for m in range(k)], full)
        loop_case = e.mk_and(inloop, e.mk_and(a_suffix, e.mk_and(a_loop, b_loop, full), full), full)
        opts.append(loop_case)
        return e.big_or(opts, full)

    # Spec must hold for every valid lasso the environment can name.
    holds = ev(phi, 0)
    e.cl(-valid_loop, holds)

    comments = (
        f"ltlsynth2dqbf source={source} n_states={n_states} k={k} encoding=unroll-lasso",
        f"semantics: SAT => REALIZABLE (<=2^{n_states} states); UNSAT inconclusive at this (n,k)",
        f"inputs={','.join(inputs)} outputs={','.join(outputs)}",
    )
    return make_formula(e.universals, e.deps, e.clauses, comments)


__all__ = ["encode", "encode_tlsf", "parse_ltl", "parse_tlsf", "TlsfSpec"]
