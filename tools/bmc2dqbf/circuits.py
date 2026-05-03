"""Parametric sequential circuits for BMC benchmark generation.

Each `circuit_*` function returns `(aag_text, comment)`. A small builder
emits ASCII AIGER directly (py-aiger isn't available on this PyPI
mirror). Inspired by HWMCC/SYNTCOMP primitives but written from scratch
here so we can sweep both bit-width and BMC bound.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

TRUE_L = 1
FALSE_L = 0


@dataclass
class B:
    """AIGER builder. Allocate inputs and latches up front (their var IDs
    must precede gates in the file), then build gates, then `set_next`."""

    n_inputs: int
    n_latches: int
    gates: list[tuple[int, int, int]] = field(default_factory=list)
    nexts: dict[int, tuple[int, int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.ins = [2 * (i + 1) for i in range(self.n_inputs)]
        self.lats = [2 * (self.n_inputs + 1 + i) for i in range(self.n_latches)]
        self._nv = self.n_inputs + self.n_latches + 1

    def gAND(self, a: int, b: int) -> int:
        if a == FALSE_L or b == FALSE_L or a == (b ^ 1):
            return FALSE_L
        if a == TRUE_L or a == b:
            return b
        if b == TRUE_L:
            return a
        lhs = 2 * self._nv
        self._nv += 1
        self.gates.append((lhs, a, b))
        return lhs

    @staticmethod
    def gNOT(a: int) -> int:
        return a ^ 1

    def gOR(self, a: int, b: int) -> int:
        return self.gNOT(self.gAND(self.gNOT(a), self.gNOT(b)))

    def gXOR(self, a: int, b: int) -> int:
        if a in (FALSE_L, TRUE_L):
            return b ^ a
        if b in (FALSE_L, TRUE_L):
            return a ^ b
        return self.gOR(self.gAND(a, self.gNOT(b)), self.gAND(self.gNOT(a), b))

    def gMUX(self, c: int, t: int, e: int) -> int:
        return self.gOR(self.gAND(c, t), self.gAND(self.gNOT(c), e))

    def all_and(self, lits: list[int]) -> int:
        out = TRUE_L
        for x in lits:
            out = self.gAND(out, x) if out != TRUE_L else x
        return out if lits else TRUE_L

    def any_or(self, lits: list[int]) -> int:
        out = FALSE_L
        for x in lits:
            out = self.gOR(out, x) if out != FALSE_L else x
        return out if lits else FALSE_L

    def set_next(self, lat: int, nxt: int, reset: int = 0) -> None:
        self.nexts[lat] = (nxt, reset)

    def aag(self, bad: int) -> str:
        m = self._nv - 1
        lines = [f"aag {m} {self.n_inputs} {self.n_latches} 1 {len(self.gates)}"]
        lines += [str(x) for x in self.ins]
        for la in self.lats:
            nxt, rst = self.nexts.get(la, (FALSE_L, 0))
            lines.append(f"{la} {nxt}" + (f" {rst}" if rst else ""))
        lines.append(str(bad))
        lines += [f"{g} {a} {b}" for g, a, b in self.gates]
        return "\n".join(lines) + "\n"


# --- circuits -------------------------------------------------------------


def circuit_counter(n: int) -> tuple[str, str]:
    """n-bit synchronous up-counter (no primary inputs).

    Latches: `l[0..n-1]` hold the counter value, LSB-first; reset = 0.
    Transition: ripple-carry +1 each cycle.
    Bad: `⋀ l[i]` — counter value is `2^n − 1`.

    Reachability: deterministic — bad first holds at step `2^n − 1`.
    BMC@k is SAT iff `k ≥ 2^n − 1` (so for N=2 SAT from k=3; N=4 from
    k=15; N=8 from k=255).
    """
    b = B(n_inputs=0, n_latches=n)
    carry = TRUE_L
    for i in range(n):
        b.set_next(b.lats[i], b.gXOR(b.lats[i], carry))
        carry = b.gAND(b.lats[i], carry)
    bad = b.all_and(list(b.lats))
    return b.aag(bad), f"counter n={n}: bad = all latches 1"


def circuit_gray(n: int) -> tuple[str, str]:
    """n-bit Gray-code generator backed by a binary counter (no inputs).

    Latches: `l[0..n-1]` are the *binary* counter state; the Gray code
    is the combinational output `g[n-1]=l[n-1]`, `g[i]=l[i+1]⊕l[i]`.
    Transition: same ripple +1 as `counter`.
    Bad: `⋀ g[i]` — Gray output is all-ones, which corresponds to
    binary value `100…0 = 2^(n-1)`.

    Reachability: deterministic — bad first holds at step `2^(n-1)`.
    BMC@k is SAT iff `k ≥ 2^(n-1)` (N=2 from k=2; N=4 from k=8; N=8
    from k=128).
    """
    b = B(n_inputs=0, n_latches=n)
    carry = TRUE_L
    for i in range(n):
        b.set_next(b.lats[i], b.gXOR(b.lats[i], carry))
        carry = b.gAND(b.lats[i], carry)
    gray = [b.lats[n - 1]] + [b.gXOR(b.lats[i + 1], b.lats[i]) for i in range(n - 1)]
    bad = b.all_and(gray)
    return b.aag(bad), f"gray n={n}: bad = Gray output all-ones"


def circuit_mutex(n: int) -> tuple[str, str]:
    """n-way fixed-priority arbiter (n request inputs, n grant latches).

    Inputs: `req[0..n-1]` per cycle.
    Latches: `grant[0..n-1]`; reset = 0.
    Transition: `grant[i]' = req[i] ∧ ¬⋁_{j<i} req[j]` — at most one
    grant is high, given to the lowest-index requester.
    Bad: `⋁_{i<j} grant[i] ∧ grant[j]` — mutual exclusion violated.

    Reachability: the arbiter is correct, so bad is unreachable.
    BMC@k is UNSAT for every k. (Serves as an "easy safe" baseline.)
    """
    b = B(n_inputs=n, n_latches=n)
    higher = FALSE_L
    for i in range(n):
        nxt = b.gAND(b.ins[i], b.gNOT(higher)) if i else b.ins[0]
        b.set_next(b.lats[i], nxt)
        higher = b.gOR(higher, b.ins[i]) if i else b.ins[0]
    pairs = [b.gAND(b.lats[i], b.lats[j]) for i in range(n) for j in range(i + 1, n)]
    bad = b.any_or(pairs)
    return b.aag(bad), f"mutex n={n}: bad = ≥2 grants"


def circuit_shift_reg(n: int) -> tuple[str, str]:
    """n-stage 1-bit shift register (one serial input).

    Input: `d` per cycle.
    Latches: `s[0..n-1]`, reset = 0.
    Transition: `s[0]'=d`, `s[i]'=s[i-1]` for `i>0`.
    Bad: `s[n-1]` — the last stage holds 1.

    Reachability: SAT iff `k ≥ n` (drive `d=1` at step 0; the 1 emerges
    at stage n-1 after n cycles). UNSAT for `k < n` regardless of input.
    """
    b = B(n_inputs=1, n_latches=n)
    for i in range(n):
        b.set_next(b.lats[i], b.ins[0] if i == 0 else b.lats[i - 1])
    return b.aag(b.lats[n - 1]), f"shift_reg n={n}: bad = stage[{n - 1}] == 1"


def circuit_fifo1(n: int) -> tuple[str, str]:
    """Depth-1 n-bit register with write-enable, checked against a shadow.

    Inputs: `we` (1 bit) + `d[0..n-1]` data.
    Latches: `r[0..n-1]` (the register) and `sd[0..n-1]` (an identical
    shadow); reset = 0.
    Transition: both `r[i]` and `sd[i]` get `we ? d[i] : self`.
    Bad: `⋁ (r[i] ⊕ sd[i])` — register and shadow differ.

    Reachability: register and shadow are wired identically, so bad is
    unreachable. BMC@k is UNSAT for every k. The interest is in the
    Tseitin/encoding cost of the n-bit MUX + XOR trees as N grows.
    """
    # inputs: we (1) + d[0..n-1]; latches: r[0..n-1] + sd[0..n-1]
    b = B(n_inputs=1 + n, n_latches=2 * n)
    we, d = b.ins[0], b.ins[1:]
    r, sd = b.lats[:n], b.lats[n:]
    for i in range(n):
        b.set_next(r[i], b.gMUX(we, d[i], r[i]))
        b.set_next(sd[i], b.gMUX(we, d[i], sd[i]))
    diffs = [b.gXOR(r[i], sd[i]) for i in range(n)]
    bad = b.any_or(diffs)
    return b.aag(bad), f"fifo1 n={n}: bad = register ≠ shadow"


def circuit_alu_add(n: int) -> tuple[str, str]:
    """Pipelined n-bit ripple-carry adder vs a one-cycle-delayed reference.

    Inputs: `a[0..n-1]`, `c[0..n-1]` operands per cycle.
    Latches: `out[0..n-1]` (registered sum), `sa[0..n-1]` and
    `sc[0..n-1]` (registered copies of the operands).
    Transition: `out' = a + c` (ripple); `sa' = a`; `sc' = c`.
    Bad: `⋁ (out[i] ⊕ ref[i])` where `ref = sa + sc` (same ripple).

    Reachability: `out` and `ref` are the same function applied at the
    same cycle, so bad is unreachable. BMC@k is UNSAT for every k.
    Stresses the encoder/solver with two n-bit ripple chains and an
    n-way XOR-OR per step.
    """
    b = B(n_inputs=2 * n, n_latches=3 * n)
    a, c = b.ins[:n], b.ins[n:]
    out, sa, sc = b.lats[:n], b.lats[n : 2 * n], b.lats[2 * n :]
    # next out = a+c (ripple carry)
    carry = FALSE_L
    for i in range(n):
        s = b.gXOR(b.gXOR(a[i], c[i]), carry)
        carry = b.gOR(b.gAND(a[i], c[i]), b.gAND(carry, b.gXOR(a[i], c[i])))
        b.set_next(out[i], s)
        b.set_next(sa[i], a[i])
        b.set_next(sc[i], c[i])
    # ref = sa+sc (same ripple)
    carry2 = FALSE_L
    diffs: list[int] = []
    for i in range(n):
        s2 = b.gXOR(b.gXOR(sa[i], sc[i]), carry2)
        carry2 = b.gOR(b.gAND(sa[i], sc[i]), b.gAND(carry2, b.gXOR(sa[i], sc[i])))
        diffs.append(b.gXOR(out[i], s2))
    bad = b.any_or(diffs)
    return b.aag(bad), f"alu_add n={n}: bad = pipelined sum ≠ reference"


REGISTRY: dict[str, Callable[[int], tuple[str, str]]] = {
    "counter": circuit_counter,
    "gray": circuit_gray,
    "mutex": circuit_mutex,
    "shift_reg": circuit_shift_reg,
    "fifo1": circuit_fifo1,
    "alu_add": circuit_alu_add,
}
