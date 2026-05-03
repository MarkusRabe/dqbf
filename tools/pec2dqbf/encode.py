"""Incomplete-circuit BMC → DQBF (Gitina et al. ICCD'13; Scholl et al. 2018).

`encode_unrolled(circ, k, blackboxes, safe=True)` builds the standard
PEC-via-BMC formula: primary inputs at every step are **universal**;
latches and gate outputs are existential with deps = all input universals
at steps ≤ t; **black-box** gate outputs are existential with deps =
*only* the input universals reachable through their operand pins at that
step. Matrix is `init ∧ ⋀_{t<k} trans_t ∧ goal`, where `goal = ⋀_t ¬bad_t`
when `safe` (the formula is TRUE iff some bb-completion is k-safe under
all inputs) and `goal = bad_k` otherwise.

`encode_succinct(circ, k, ...)` emits the step relation **exactly once**
over a universal step-index pair (t, t'); state, input and gate signals
become existential *functions* of the index. This compresses the formula
to size independent of k but answers a weaker question (inputs are no
longer ∀ per step — they are an ∃ trace function); use it for benchmark
generation, not for exact PEC equivalence. See the module CLAUDE.md.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from core.formula import Formula, make_formula
from tools.pec2dqbf.aiger_seq import SeqAig


@dataclass
class _Builder:
    universals: list[int] = field(default_factory=list)
    deps: dict[int, frozenset[int]] = field(default_factory=dict)
    clauses: list[list[int]] = field(default_factory=list)
    _next: int = 1

    def fresh_u(self) -> int:
        v = self._next
        self._next += 1
        self.universals.append(v)
        return v

    def fresh_e(self, deps: Iterable[int]) -> int:
        v = self._next
        self._next += 1
        self.deps[v] = frozenset(deps)
        return v

    def add(self, *cs: list[int]) -> None:
        self.clauses.extend(cs)

    def tseitin_and(self, out: int, a: int, b: int) -> None:
        self.add([-out, a], [-out, b], [out, -a, -b])

    def eq(self, x: int, y: int) -> None:
        self.add([-x, y], [x, -y])


def _map_lit(aiglit: int, alit: dict[int, int], true_var: int) -> int:
    """Map an AIGER literal (with constant 0/1) to a DQBF literal."""
    v = aiglit & ~1
    sgn = -1 if aiglit & 1 else 1
    if v == 0:
        return sgn * (-true_var)  # AIGER 0=FALSE → -TRUE; AIGER 1=TRUE → TRUE
    return sgn * alit[v]


def _emit_gate(g: int, a: int, b: int, B: _Builder, alit: dict[int, int], true_var: int) -> None:
    B.tseitin_and(alit[g], _map_lit(a, alit, true_var), _map_lit(b, alit, true_var))


def encode_unrolled(circ: SeqAig, k: int, blackboxes: set[int], safe: bool = True) -> Formula:
    B = _Builder()
    TRUE = B.fresh_e(())
    B.add([TRUE])
    bb = set(blackboxes)
    src_inputs = set(circ.inputs)
    leaves = src_inputs | {lat.lit for lat in circ.latches}

    step_alit: list[dict[int, int]] = []
    step_input_u: list[set[int]] = []

    for t in range(k + 1):
        alit: dict[int, int] = {}
        ins_u: set[int] = set()
        for ai in circ.inputs:
            v = B.fresh_u()
            alit[ai] = v
            ins_u.add(v)
        step_input_u.append(ins_u)
        prior_u: frozenset[int] = frozenset().union(*step_input_u[:t]) if t > 0 else frozenset()
        for lat in circ.latches:
            alit[lat.lit] = B.fresh_e(prior_u)
        all_u_upto = prior_u | ins_u
        for g, a, b in circ.gates:
            if g in bb:
                cone = circ.cone_inputs(a, leaves) | circ.cone_inputs(b, leaves)
                d = {alit[x] for x in cone if x in src_inputs}
                alit[g] = B.fresh_e(d)
            else:
                alit[g] = B.fresh_e(all_u_upto)
                _emit_gate(g, a, b, B, alit, TRUE)
        step_alit.append(alit)

    for lat in circ.latches:
        v0 = step_alit[0][lat.lit]
        B.add([v0] if lat.reset == 1 else [-v0])

    for t in range(k):
        cur, nxt = step_alit[t], step_alit[t + 1]
        for lat in circ.latches:
            B.eq(nxt[lat.lit], _map_lit(lat.next, cur, TRUE))

    bad_at = [_map_lit(circ.bad, step_alit[t], TRUE) for t in range(k + 1)]
    if safe:
        for b in bad_at:
            B.add([-b])
    else:
        B.add([bad_at[k]])

    return make_formula(B.universals, B.deps, B.clauses)


def encode_succinct(circ: SeqAig, k: int, blackboxes: set[int], safe: bool = True) -> Formula:
    B = _Builder()
    TRUE = B.fresh_e(())
    B.add([TRUE])
    bb = set(blackboxes)
    nbits = max(1, math.ceil(math.log2(k + 1)) if k > 0 else 1)
    t_bits = [B.fresh_u() for _ in range(nbits)]
    tp_bits = [B.fresh_u() for _ in range(nbits)]

    def idx_is(bits: list[int], val: int) -> list[int]:
        return [(bits[i] if (val >> i) & 1 else -bits[i]) for i in range(len(bits))]

    def frame(bits: list[int], emit_gates: bool) -> dict[int, int]:
        d_bits = frozenset(bits)
        alit: dict[int, int] = {}
        for ai in circ.inputs:
            alit[ai] = B.fresh_e(d_bits)
        for lat in circ.latches:
            alit[lat.lit] = B.fresh_e(d_bits)
        for g, a, b in circ.gates:
            alit[g] = B.fresh_e(d_bits)
            if emit_gates and g not in bb:
                _emit_gate(g, a, b, B, alit, TRUE)
        return alit

    cur = frame(t_bits, emit_gates=True)
    nxt = frame(tp_bits, emit_gates=False)

    # Same-function constraint: (t == t') → cur_v == nxt_v for every signal.
    # Build EQ ↔ ⋀_i (t_i ↔ t'_i), then ¬EQ ∨ (cur_v ↔ nxt_v).
    all_idx = frozenset(t_bits + tp_bits)
    bit_eq: list[int] = []
    for ti, tpi in zip(t_bits, tp_bits, strict=True):
        e = B.fresh_e(all_idx)
        B.add([-e, -ti, tpi], [-e, ti, -tpi], [e, ti, tpi], [e, -ti, -tpi])
        bit_eq.append(e)
    EQ = B.fresh_e(all_idx)
    for e in bit_eq:
        B.add([-EQ, e])
    B.add([EQ] + [-e for e in bit_eq])
    for key in cur:
        a, b = cur[key], nxt[key]
        B.add([-EQ, -a, b], [-EQ, a, -b])

    g0 = [-x for x in idx_is(t_bits, 0)]
    for lat in circ.latches:
        v = cur[lat.lit]
        B.add(g0 + ([v] if lat.reset == 1 else [-v]))

    for tv in range(k):
        guard = [-x for x in idx_is(t_bits, tv)] + [-x for x in idx_is(tp_bits, tv + 1)]
        for lat in circ.latches:
            target = _map_lit(lat.next, cur, TRUE)
            B.add(guard + [-nxt[lat.lit], target], guard + [nxt[lat.lit], -target])

    bad_cur = _map_lit(circ.bad, cur, TRUE)
    if safe:
        B.add([-bad_cur])
    else:
        B.add([-x for x in idx_is(t_bits, k)] + [bad_cur])

    return make_formula(B.universals, B.deps, B.clauses)


def encode(
    circ: SeqAig,
    k: int,
    blackboxes: Iterable[int] = (),
    mode: str = "unrolled",
    safe: bool = True,
    source: str = "<memory>",
) -> Formula:
    bb = set(blackboxes)
    if mode == "unrolled":
        f = encode_unrolled(circ, k, bb, safe=safe)
    elif mode == "succinct":
        f = encode_succinct(circ, k, bb, safe=safe)
    else:
        raise ValueError(f"unknown mode {mode!r}")
    comments = (
        f"pec2dqbf source={source} bound={k} mode={mode} safe={safe} blackboxes={sorted(bb)}",
        f"circuit: I={len(circ.inputs)} L={len(circ.latches)} A={len(circ.gates)}",
    )
    return make_formula(f.universals, f.dependencies, f.clauses, comments)
