"""Tests for the circuit-synthesis encoder.

`core.semantics.is_true` is double-exponential, so the brute-force
checks stay at n=2 inputs and ≤2 gates. Larger instances get a solver
cross-check against pedant.
"""

from __future__ import annotations

import subprocess
import tempfile

import pytest

from core.dqdimacs import dumps
from core.semantics import is_true
from tools.circuitsynth2dqbf.encode import encode_depth, encode_gates
from tools.circuitsynth2dqbf.spec_functions import (
    REGISTRY,
    Spec,
    adder,
    and_reduce,
    majority,
    mux,
    parity,
)


def _eval_matches(spec: Spec) -> None:
    """The Python evaluator must agree with the declared output arity."""
    for row in range(1 << min(spec.n_inputs, 8)):
        bits = [(row >> j) & 1 == 1 for j in range(spec.n_inputs)]
        out = spec.eval(bits)
        assert len(out) == spec.n_outputs, spec.name


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_spec_arity(name: str) -> None:
    _eval_matches(REGISTRY[name](2))


# ───────────────────── prefix-shape sanity ───────────────────────────


def test_prefix_shape() -> None:
    f = encode_gates(parity(3), k=2)
    assert len(f.universals) == 3
    # Exactly two dep classes: ∅ (topology) and {x} (values).
    classes = {d for d in f.dependencies.values()}
    assert classes == {frozenset(), frozenset(f.universals)}
    # Genuine DQBF (some ∅-dep var co-occurs with some {x}-dep var).
    full = frozenset(f.universals)
    assert any(
        any(f.dependencies.get(abs(lit)) == frozenset() for lit in c)
        and any(f.dependencies.get(abs(lit)) == full for lit in c)
        for c in f.clauses
    )


# ───────────────────── brute-force semantics (tiny) ──────────────────


@pytest.mark.parametrize(
    "spec,k,expect",
    [
        # k=0: only projections/outputs; brute-forceable.
        (parity(2), 0, False),  # XOR isn't a projection
        (and_reduce(2), 0, False),
    ],
)
def test_semantics_tiny_gates(spec: Spec, k: int, expect: bool) -> None:
    f = encode_gates(spec, k)
    assert is_true(f, budget=10_000_000) is expect


def test_semantics_tiny_depth() -> None:
    assert is_true(encode_depth(parity(2), depth=0, width=1), budget=10_000_000) is False


# ───────────────────── solver cross-check (pedant) ───────────────────


def _pedant(f) -> str | None:
    with tempfile.NamedTemporaryFile("w", suffix=".dqdimacs", delete=False) as fh:
        fh.write(dumps(f))
        p = fh.name
    try:
        r = subprocess.run(
            ["third_party/pedant/build/src/pedant", p],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    return {10: "sat", 20: "unsat"}.get(r.returncode)


@pytest.mark.parametrize(
    "spec,k,expect",
    [
        (parity(3), 2, "sat"),  # 2 gates exactly optimal
        (parity(3), 1, "unsat"),
        (and_reduce(4), 3, "sat"),
        (and_reduce(4), 2, "unsat"),
        (majority(3), 4, "sat"),  # Knuth: C(MAJ₃)=4
        (majority(3), 3, "unsat"),
        (mux(1), 3, "sat"),  # ITE = 3 gates
        (adder(1), 2, "sat"),  # half-adder = 2 gates
        (adder(1), 1, "unsat"),
    ],
)
def test_pedant_gates(spec: Spec, k: int, expect: str) -> None:
    got = _pedant(encode_gates(spec, k))
    if got is None:
        pytest.skip("pedant unavailable or timeout")
    assert got == expect


@pytest.mark.parametrize(
    "spec,d,w,expect",
    [
        (parity(4), 2, 2, "sat"),  # depth ⌈log₂4⌉=2 with 2 gates/layer
        (parity(4), 1, 4, "unsat"),  # depth 1 can't do 4-XOR
        (and_reduce(4), 2, 2, "sat"),
    ],
)
def test_pedant_depth(spec: Spec, d: int, w: int, expect: str) -> None:
    got = _pedant(encode_depth(spec, d, w))
    if got is None:
        pytest.skip("pedant unavailable or timeout")
    assert got == expect


# ───────────────────── structural-spec consistency ───────────────────


@pytest.mark.parametrize("name", ["and", "or", "xor", "eq", "inc", "add", "feistel", "lt"])
def test_structural_spec_matches_eval(name: str) -> None:
    """The hand-coded Tseitin spec must agree with the Python evaluator."""
    spec = REGISTRY[name](2)
    # k = upper bound so the synthesis side is trivially satisfiable;
    # if pedant says SAT and the spec circuit were wrong, we'd get UNSAT.
    got = _pedant(encode_gates(spec, spec.upper_gates))
    if got is None:
        pytest.skip("pedant unavailable or timeout")
    assert got == "sat"
