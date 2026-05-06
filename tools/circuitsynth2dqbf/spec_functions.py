"""Target-function library for circuit-synthesis benchmarks.

Each `Spec` describes one Boolean function family parametrised by
bitwidth `n`: number of inputs/outputs, a Python reference evaluator
(ground truth for the spec circuit and for tests), and known minimal
gate/depth bounds over the full binary basis B₂ where the literature
gives them. ``None`` means we don't have a closed-form optimum — the
generator then sweeps a small window around the trivial upper bound.

Gate-count optima over B₂ (all 16 two-input Boolean functions) follow
Knuth, *TAOCP* 7.1.2, and Kojevnikov–Kulikov–Yaroslavtsev, "Finding
Efficient Circuits Using SAT-Solvers" (SAT 2009). Depth optima for
balanced reductions are ⌈log₂ n⌉.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Spec:
    name: str
    n_inputs: int
    n_outputs: int
    eval: Callable[[list[bool]], list[bool]]
    known_gates: int | None
    known_depth: int | None
    upper_gates: int  # a witnessed upper bound (some circuit of this size exists)
    upper_depth: int


def _bits2int(x: list[bool]) -> int:
    v = 0
    for i, b in enumerate(x):
        v |= int(b) << i
    return v


def _int2bits(v: int, n: int) -> list[bool]:
    return [(v >> i) & 1 == 1 for i in range(n)]


def _ceil_log2(n: int) -> int:
    return max(1, math.ceil(math.log2(max(n, 2))))


# ───────────────────────────── builders ──────────────────────────────


def and_reduce(n: int) -> Spec:
    return Spec(
        name=f"and{n}",
        n_inputs=n,
        n_outputs=1,
        eval=lambda x: [all(x)],
        known_gates=n - 1,
        known_depth=_ceil_log2(n),
        upper_gates=n - 1,
        upper_depth=_ceil_log2(n),
    )


def or_reduce(n: int) -> Spec:
    return Spec(
        name=f"or{n}",
        n_inputs=n,
        n_outputs=1,
        eval=lambda x: [any(x)],
        known_gates=n - 1,
        known_depth=_ceil_log2(n),
        upper_gates=n - 1,
        upper_depth=_ceil_log2(n),
    )


def parity(n: int) -> Spec:
    return Spec(
        name=f"xor{n}",
        n_inputs=n,
        n_outputs=1,
        eval=lambda x: [sum(x) % 2 == 1],
        known_gates=n - 1,
        known_depth=_ceil_log2(n),
        upper_gates=n - 1,
        upper_depth=_ceil_log2(n),
    )


def majority(n: int) -> Spec:
    # Knuth 7.1.2: C(MAJ₃)=4, C(MAJ₅)=10. No closed form.
    known = {3: 4, 5: 10, 7: 19}.get(n)
    # Upper bound: sorting-network style, O(n log n); use a loose 4n.
    return Spec(
        name=f"maj{n}",
        n_inputs=n,
        n_outputs=1,
        eval=lambda x: [sum(x) > len(x) // 2],
        known_gates=known,
        known_depth=None,
        upper_gates=known or 4 * n,
        upper_depth=2 * _ceil_log2(n),
    )


def exactly_k(n: int, k: int) -> Spec:
    return Spec(
        name=f"exact{k}of{n}",
        n_inputs=n,
        n_outputs=1,
        eval=lambda x: [sum(x) == k],
        known_gates=None,
        known_depth=None,
        upper_gates=5 * n,
        upper_depth=2 * _ceil_log2(n) + 2,
    )


def threshold_k(n: int, k: int) -> Spec:
    return Spec(
        name=f"thresh{k}of{n}",
        n_inputs=n,
        n_outputs=1,
        eval=lambda x: [sum(x) >= k],
        known_gates=None,
        known_depth=None,
        upper_gates=5 * n,
        upper_depth=2 * _ceil_log2(n) + 2,
    )


def equality(n: int) -> Spec:
    # a == b for two n-bit words. n XNORs + (n-1)-AND = 2n-1.
    return Spec(
        name=f"eq{n}",
        n_inputs=2 * n,
        n_outputs=1,
        eval=lambda x: [x[:n] == x[n:]],
        known_gates=2 * n - 1,
        known_depth=_ceil_log2(n) + 1,
        upper_gates=2 * n - 1,
        upper_depth=_ceil_log2(n) + 1,
    )


def less_than(n: int) -> Spec:
    return Spec(
        name=f"lt{n}",
        n_inputs=2 * n,
        n_outputs=1,
        eval=lambda x: [_bits2int(x[:n]) < _bits2int(x[n:])],
        known_gates=None,
        known_depth=None,
        upper_gates=5 * n,
        upper_depth=2 * _ceil_log2(n),
    )


def adder(n: int) -> Spec:
    # n+n → n+1. Full adder = 5 gates over B₂; ripple = 5n - 3 (first
    # cell is a half-adder, 2 gates). Known optimal for n=1: 2 (HA).
    return Spec(
        name=f"add{n}",
        n_inputs=2 * n,
        n_outputs=n + 1,
        eval=lambda x: _int2bits(_bits2int(x[:n]) + _bits2int(x[n:]), n + 1),
        known_gates=2 if n == 1 else None,
        known_depth=None,
        upper_gates=max(2, 5 * n - 3),
        upper_depth=2 * n,
    )


def incrementer(n: int) -> Spec:
    return Spec(
        name=f"inc{n}",
        n_inputs=n,
        n_outputs=n + 1,
        eval=lambda x: _int2bits(_bits2int(x) + 1, n + 1),
        known_gates=None,
        known_depth=None,
        upper_gates=2 * n,
        upper_depth=n,
    )


def multiplier(n: int) -> Spec:
    return Spec(
        name=f"mul{n}",
        n_inputs=2 * n,
        n_outputs=2 * n,
        eval=lambda x: _int2bits(_bits2int(x[:n]) * _bits2int(x[n:]), 2 * n),
        known_gates=None,
        known_depth=None,
        upper_gates=6 * n * n,
        upper_depth=4 * n,
    )


def popcount(n: int) -> Spec:
    m = n.bit_length()
    return Spec(
        name=f"popcnt{n}",
        n_inputs=n,
        n_outputs=m,
        eval=lambda x: _int2bits(sum(x), m),
        known_gates=None,
        known_depth=None,
        upper_gates=5 * n,
        upper_depth=2 * _ceil_log2(n),
    )


def leading_zero_count(n: int) -> Spec:
    m = (n).bit_length()

    def ev(x: list[bool]) -> list[bool]:
        c = 0
        for b in reversed(x):
            if b:
                break
            c += 1
        return _int2bits(c, m)

    return Spec(
        name=f"lzc{n}",
        n_inputs=n,
        n_outputs=m,
        eval=ev,
        known_gates=None,
        known_depth=None,
        upper_gates=4 * n,
        upper_depth=2 * _ceil_log2(n),
    )


def mux(n: int) -> Spec:
    # 2ⁿ-to-1 mux: n select bits + 2ⁿ data bits → 1. C(ITE)=3; tree of
    # 2ⁿ-1 ITEs = 3·(2ⁿ-1). Known optimal for n=1: 3.
    d = 1 << n
    return Spec(
        name=f"mux{n}",
        n_inputs=n + d,
        n_outputs=1,
        eval=lambda x: [x[n + _bits2int(x[:n])]],
        known_gates=3 if n == 1 else None,
        known_depth=2 if n == 1 else None,
        upper_gates=3 * (d - 1),
        upper_depth=2 * n,
    )


def priority_encoder(n: int) -> Spec:
    m = n.bit_length()

    def ev(x: list[bool]) -> list[bool]:
        for i in range(n - 1, -1, -1):
            if x[i]:
                return _int2bits(i, m) + [True]
        return [False] * m + [False]

    return Spec(
        name=f"prienc{n}",
        n_inputs=n,
        n_outputs=m + 1,
        eval=ev,
        known_gates=None,
        known_depth=None,
        upper_gates=4 * n,
        upper_depth=2 * _ceil_log2(n),
    )


def onehot_decoder(n: int) -> Spec:
    d = 1 << n
    return Spec(
        name=f"onehot{n}",
        n_inputs=n,
        n_outputs=d,
        eval=lambda x: [i == _bits2int(x) for i in range(d)],
        known_gates=None,
        known_depth=None,
        upper_gates=2 * d,
        upper_depth=_ceil_log2(n) + 1,
    )


def feistel_round(n: int) -> Spec:
    """One Feistel round with a fixed quadratic S-box: (L,R) → (R, L ⊕ F(R))
    where F(r)_i = r_i ∧ r_{(i+1) mod n}. Inputs/outputs are 2n bits."""

    def ev(x: list[bool]) -> list[bool]:
        L, R = x[:n], x[n:]
        f = [R[i] and R[(i + 1) % n] for i in range(n)]
        return R + [L[i] ^ f[i] for i in range(n)]

    return Spec(
        name=f"feistel{n}",
        n_inputs=2 * n,
        n_outputs=2 * n,
        eval=ev,
        known_gates=None,
        known_depth=None,
        upper_gates=2 * n,
        upper_depth=2,
    )


def fp_add(e: int, m: int) -> Spec:
    """Unsigned floating-point add for the tiny formats E{e}M{m}: no sign
    bit, no subnormals, ties-to-even ignored (truncate). The point is a
    nontrivial multi-output spec, not IEEE conformance."""
    n = e + m

    def decode(bits: list[bool]) -> tuple[int, int]:
        E = _bits2int(bits[m:])
        M = _bits2int(bits[:m])
        return E, M | (1 << m)  # implicit leading 1

    def ev(x: list[bool]) -> list[bool]:
        ea, ma = decode(x[:n])
        eb, mb = decode(x[n:])
        if ea < eb:
            ea, ma, eb, mb = eb, mb, ea, ma
        mb >>= ea - eb
        s = ma + mb
        E = ea
        if s >> (m + 1):
            s >>= 1
            E += 1
        E = min(E, (1 << e) - 1)
        return _int2bits(s & ((1 << m) - 1), m) + _int2bits(E, e)

    return Spec(
        name=f"fpaddE{e}M{m}",
        n_inputs=2 * n,
        n_outputs=n,
        eval=ev,
        known_gates=None,
        known_depth=None,
        upper_gates=20 * n,
        upper_depth=4 * n,
    )


# ─────────────────────────── registry ────────────────────────────────

REGISTRY: dict[str, Callable[[int], Spec]] = {
    "and": and_reduce,
    "or": or_reduce,
    "xor": parity,
    "maj": majority,
    "exact1": lambda n: exactly_k(n, 1),
    "exacthalf": lambda n: exactly_k(n, n // 2),
    "thresh2": lambda n: threshold_k(n, 2),
    "eq": equality,
    "lt": less_than,
    "add": adder,
    "inc": incrementer,
    "mul": multiplier,
    "popcnt": popcount,
    "lzc": leading_zero_count,
    "mux": mux,
    "prienc": priority_encoder,
    "onehot": onehot_decoder,
    "feistel": feistel_round,
    "fpadd23": lambda n: fp_add(2, 3),
    "fpadd32": lambda n: fp_add(3, 2),
}

WIDTHS = (2, 4, 8, 16, 32, 64)

# Per-function width caps — beyond these the encoding exceeds ~50k vars,
# the spec semantics stop making sense (mux input count = 2ⁿ), or the
# function has no structural spec builder so the truth-table fallback
# (n_inputs ≤ 10) bounds it.
WIDTH_CAP: dict[str, int] = {
    "mul": 4,
    "mux": 2,
    "onehot": 4,
    "add": 8,
    "inc": 16,
    "popcnt": 8,
    "lzc": 8,
    "prienc": 8,
    "lt": 8,
    "eq": 16,
    "feistel": 16,
    "fpadd23": 2,  # width param ignored
    "fpadd32": 2,
    "maj": 8,
    "exact1": 8,
    "exacthalf": 8,
    "thresh2": 8,
}
