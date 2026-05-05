"""Verify circuits_v3 builders produce well-formed AIGER and that the
claimed ``k_bad`` matches simulation. The ``expected`` field in the
generated manifest is derived from ``k_bad``, so a wrong value here
would poison the benchmark ground truth.
"""

from __future__ import annotations

import random

import pytest

from tools.bmc2dqbf.circuits_v3 import REGISTRY_V3
from tools.pec2dqbf.aiger_seq import SeqAig, parse_seq_aag


def _eval(vals: dict[int, int], lit: int) -> int:
    if lit < 2:
        return lit
    return vals[lit & ~1] ^ (lit & 1)


def _reset(seq: SeqAig) -> dict[int, int]:
    return {la.lit: (la.reset if la.reset in (0, 1) else 0) for la in seq.latches}


def _trace_bad(seq: SeqAig, input_fn, horizon: int) -> int | None:
    """Smallest t with bad(state_t)=1, state_0=reset, state_{t+1}=T(state_t,in_t)."""
    vals: dict[int, int] = {}
    st = _reset(seq)
    for t in range(horizon + 1):
        vals.clear()
        inp = input_fn(t)
        for i, lit in enumerate(seq.inputs):
            vals[lit] = inp[i]
        for la in seq.latches:
            vals[la.lit] = st[la.lit]
        for g, a, b in seq.gates:
            vals[g] = _eval(vals, a) & _eval(vals, b)
        if _eval(vals, seq.bad):
            return t
        st = {la.lit: _eval(vals, la.next) for la in seq.latches}
    return None


@pytest.mark.parametrize("name", sorted(REGISTRY_V3))
@pytest.mark.parametrize("n", [4, 8])
def test_aag_well_formed(name: str, n: int) -> None:
    for bug in (False, True):
        aag, comment, k_bad = REGISTRY_V3[name](n, bug)
        seq = parse_seq_aag(aag)
        assert seq.bad != 0, f"{name}: bad output is constant-false"
        assert len(seq.latches) > 0
        assert (k_bad is None) == (not bug), f"{name}: k_bad/bug mismatch"


@pytest.mark.parametrize("name", sorted(REGISTRY_V3))
def test_safe_unreachable(name: str) -> None:
    """Safe variant: bad never fires under random inputs for 200 steps."""
    rng = random.Random(0xC0FFEE ^ hash(name))
    for n in (4, 6):
        aag, _, k_bad = REGISTRY_V3[name](n, bug=False)
        assert k_bad is None
        seq = parse_seq_aag(aag)
        for _ in range(5):
            inp = lambda t: [rng.randint(0, 1) for _ in seq.inputs]  # noqa: E731,B023
            assert _trace_bad(seq, inp, horizon=200) is None, (
                f"{name} n={n} safe variant reached bad"
            )


def _witness_patterns(ni: int, k_bad: int, seed: int) -> list:
    """Heuristic + random input traces, each: t → list[int] of length ni."""
    fixed = [
        [1] * ni,
        [0] * ni,
        [1 if i == ni - 1 else 0 for i in range(ni)],
        [1 if i == 0 else 0 for i in range(ni)],
    ]
    out: list = [(lambda t, v=v: v) for v in fixed]
    out.append(lambda t, m=ni: [1 if t == 0 else 0] * m)
    out.append(lambda t, m=ni: [(t + i) & 1 for i in range(m)])
    rng = random.Random(seed)
    for _ in range(30):
        bits = [rng.randint(0, 1) for _ in range(ni * (k_bad + 2))]
        out.append(lambda t, b=bits, m=ni: b[t * m : (t + 1) * m] or [0] * m)
    return out


@pytest.mark.parametrize("name", sorted(REGISTRY_V3))
def test_bug_reachable_at_k_bad(name: str) -> None:
    """Bug variant: some input trace reaches bad within k_bad steps."""
    for n in (4, 6):
        aag, _, k_bad = REGISTRY_V3[name](n, bug=True)
        assert k_bad is not None
        seq = parse_seq_aag(aag)
        hit = None
        for p in _witness_patterns(len(seq.inputs), k_bad, 0xBADC0DE ^ hash(name) ^ n):
            r = _trace_bad(seq, p, horizon=k_bad + 1)
            if r is not None:
                hit = r if hit is None else min(hit, r)
                if hit <= k_bad:
                    break
        assert hit is not None, f"{name} n={n}: bug variant never reached bad"
        assert hit <= k_bad, f"{name} n={n}: bad at {hit} but k_bad={k_bad}"
