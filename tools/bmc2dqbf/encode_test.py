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
    # reach-bad (∃t≤k. bad_t): s=0,1,0,... → True for k≥1.
    assert is_true(encode(c, k=0)) is False
    assert is_true(encode(c, k=1)) is True
    assert is_true(encode(c, k=2)) is True
    assert is_true(encode(c, k=0, safe=True)) is True
    assert is_true(encode(c, k=1, safe=True)) is False


def test_copy_input_reachability() -> None:
    """∃i. bad_t = l0 = i_{t-1}. Reachable at k≥1 (set i_0=1)."""
    c = parse_seq_aag(COPY_INPUT)
    assert is_true(encode(c, k=1)) is True
    assert is_true(encode(c, k=1, safe=True)) is False
    assert is_true(encode(c, k=1, forall_inputs=True)) is False


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
    assert len(f3.universals) == 0  # ∃-inputs by default
    assert len(encode(c, k=3, safe=True).universals) == 4 * len(c.inputs)
    assert f3.n_vars > f1.n_vars


def test_comment_header() -> None:
    c = parse_seq_aag(TOGGLE)
    f = encode(c, k=2, source="toggle.aag")
    assert any("bmc2dqbf" in cm and "toggle.aag" in cm for cm in f.comments)
