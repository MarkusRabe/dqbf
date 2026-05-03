from __future__ import annotations

from core.semantics import is_true
from tools.bmc2dqbf.encode import encode
from tools.pec2dqbf.aiger_seq import parse_seq_aag

# 1 latch s (lit 2), no inputs. next = ¬s. bad = s. Reset 0.
TOGGLE = "aag 1 0 1 1 0\n2 3\n2\n"

# 1 input i (lit 2), 1 latch s (lit 4), next = i. bad = s.
COPY_INPUT = "aag 2 1 1 1 0\n2\n4 2\n4\n"

# 2-bit counter: l0 (2), l1 (4); l0' = ¬l0; l1' = l0⊕l1. bad = l0∧l1.
# g6 = l0∧l1; g8 = ¬l0∧¬l1; g10 = ¬g6∧¬g8 = l0⊕l1.
COUNTER2 = "aag 5 0 2 1 3\n2 3\n4 10\n6\n6 2 4\n8 3 5\n10 7 9\n"


def test_toggle() -> None:
    c = parse_seq_aag(TOGGLE)
    # reach-bad: s_0=0 → bad_0 fails; s_1=1 → bad_1 holds; s_2=0 → bad_2 fails.
    assert is_true(encode(c, k=0)) is False
    assert is_true(encode(c, k=1)) is True
    assert is_true(encode(c, k=2)) is False
    # safe: stays safe at k=0, fails from k=1.
    assert is_true(encode(c, k=0, safe=True)) is True
    assert is_true(encode(c, k=1, safe=True)) is False


def test_copy_input_is_qbf() -> None:
    """All deps are nested → QBF. ∀i. bad_1 = i_0 — fails for i_0=0, so FALSE."""
    c = parse_seq_aag(COPY_INPUT)
    f = encode(c, k=1)
    # nestedness: each existential's dep set is some prefix of universals.
    us = list(f.universals)
    for d in f.dependencies.values():
        assert any(d == frozenset(us[:i]) for i in range(len(us) + 1))
    assert is_true(f) is False


def test_counter2_reaches_11_at_k3() -> None:
    """00→01→10→11. bad = l0∧l1 first holds at step 3."""
    c = parse_seq_aag(COUNTER2)
    for k, expected in [(0, False), (1, False), (2, False), (3, True)]:
        assert is_true(encode(c, k=k), budget=5_000_000) is expected, k
    assert is_true(encode(c, k=2, safe=True)) is True
    assert is_true(encode(c, k=3, safe=True), budget=5_000_000) is False


def test_var_counts() -> None:
    c = parse_seq_aag(COPY_INPUT)
    f1, f3 = encode(c, k=1), encode(c, k=3)
    assert len(f3.universals) == 4 * len(c.inputs)
    assert f3.n_vars > f1.n_vars


def test_comment_header() -> None:
    c = parse_seq_aag(TOGGLE)
    f = encode(c, k=2, source="toggle.aag")
    assert any("bmc2dqbf" in cm and "toggle.aag" in cm for cm in f.comments)
