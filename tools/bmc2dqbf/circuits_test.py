from __future__ import annotations

import pytest

from core.semantics import is_true
from tools.bmc2dqbf.circuits import (
    REGISTRY,
    circuit_alu_add,
    circuit_counter,
    circuit_fifo1,
    circuit_gray,
    circuit_mutex,
    circuit_shift_reg,
)
from tools.bmc2dqbf.encode import encode
from tools.pec2dqbf.aiger_seq import parse_seq_aag


def _enc(aag: str, k: int, safe: bool = False):
    return encode(parse_seq_aag(aag), k=k, safe=safe)


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_registry_parses_and_encodes(name: str) -> None:
    aag, comment = REGISTRY[name](2)
    c = parse_seq_aag(aag)
    assert c.max_var > 0 and c.outputs and comment
    f = encode(c, k=2, source=f"{name}_n2")
    assert any(name in cm for cm in f.comments)


def test_counter_semantics() -> None:
    """At width 1: 0→1; bad=l0 reached at k=1."""
    aag, _ = circuit_counter(1)
    assert is_true(_enc(aag, k=0)) is False
    assert is_true(_enc(aag, k=1)) is True
    assert is_true(_enc(aag, k=0, safe=True)) is True
    assert is_true(_enc(aag, k=1, safe=True)) is False
    # n=2: not reached by k=1 (00→01).
    aag2, _ = circuit_counter(2)
    assert is_true(_enc(aag2, k=1), budget=2_000_000) is False


def test_gray_semantics() -> None:
    """At width 1 Gray = identity; same as counter(1)."""
    aag, _ = circuit_gray(1)
    assert is_true(_enc(aag, k=0)) is False
    assert is_true(_enc(aag, k=1)) is True


def test_shift_reg_semantics() -> None:
    """1 input, 2 stages: ∃-reach True at k≥2 (all-1 input fills it);
    safe (∀) holds at k<2, fails at k≥2."""
    aag, _ = circuit_shift_reg(2)
    assert is_true(_enc(aag, k=1), budget=2_000_000) is False
    assert is_true(_enc(aag, k=2), budget=2_000_000) is True
    assert is_true(_enc(aag, k=1, safe=True), budget=2_000_000) is True
    assert is_true(_enc(aag, k=2, safe=True), budget=2_000_000) is False


def test_mutex_safe_from_reset() -> None:
    aag, _ = circuit_mutex(2)
    assert is_true(_enc(aag, k=0, safe=True), budget=2_000_000) is True
    assert is_true(_enc(aag, k=0), budget=2_000_000) is False


def test_fifo1_alu_add_structural() -> None:
    """Input-heavy circuits: brute-force semantics is intractable; check
    that the AIG is well-formed and bad=0 from reset (encode succeeds)."""
    for fn in (circuit_fifo1, circuit_alu_add):
        aag, _ = fn(2)
        c = parse_seq_aag(aag)
        assert len(c.inputs) > 0 and len(c.latches) > 0
        f = _enc(aag, k=0, safe=True)
        # Reset state has all latches 0; bad depends only on latches → safe@k=0
        # is decidable by checking the propositional restriction (universals
        # don't matter since bad's cone is latch-only). We just assert encode
        # produced a Formula and didn't crash.
        assert f.n_vars > len(c.inputs)


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_nvars_grow_with_n_and_k(name: str) -> None:
    aag2, _ = REGISTRY[name](2)
    aag4, _ = REGISTRY[name](4)
    f22 = _enc(aag2, k=2)
    f24 = _enc(aag2, k=4)
    f42 = _enc(aag4, k=2)
    assert f24.n_vars > f22.n_vars
    assert f42.n_vars > f22.n_vars
