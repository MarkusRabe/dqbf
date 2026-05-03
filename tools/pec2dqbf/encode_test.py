"""Tests for pec2dqbf against the brute-force semantics oracle.

Circuits are tiny so `core.semantics.is_true` decides them.
"""

from __future__ import annotations

import pytest

from core.semantics import is_true
from tools.pec2dqbf.aiger_seq import parse_seq_aag
from tools.pec2dqbf.encode import encode

# 1 latch s (lit 2), no inputs. next = ¬s (lit 3). bad = s.
# Reset 0. Trace: s_0=0, s_1=1, s_2=0, ...
TOGGLE = "aag 1 0 1 1 0\n2 3\n2\n"

# 1 input i (lit 2), 1 latch s (lit 4), next = i. bad = s.
# s_0=0, s_1=i_0, s_2=i_1, ...
COPY_INPUT = "aag 2 1 1 1 0\n2\n4 2\n4\n"

# 1 input i (2), 1 latch s (4), 1 gate g6 = s ∧ i. next = g6. bad = s.
# Black-box g6 → next = bb(s,i). Question (safe): ∃bb. ∀i. never bad.
# s_0=0; s_1=bb(0,i_0). For safety we need bb(0,·)=0. So TRUE (bb≡0 works).
WITH_BB = "aag 3 1 1 1 1\n2\n4 6\n4\n6 4 2\n"

# Same circuit, bad = ¬s (lit 5). s_0=0 → bad_0=1 immediately. No bb can help.
WITH_BB_UNSAFE = "aag 3 1 1 1 1\n2\n4 6\n5\n6 4 2\n"


def test_parse_seq() -> None:
    c = parse_seq_aag(WITH_BB)
    assert c.inputs == [2]
    assert len(c.latches) == 1 and c.latches[0].lit == 4 and c.latches[0].next == 6
    assert c.bad == 4
    assert c.gates == [(6, 4, 2)]


@pytest.mark.parametrize("mode", ["unrolled", "succinct"])
def test_toggle_no_inputs(mode: str) -> None:
    c = parse_seq_aag(TOGGLE)
    # safe=True: ¬bad at all steps. s_0=0 ok; s_1=1 violates → FALSE for k≥1.
    f0 = encode(c, k=0, mode=mode, safe=True)
    f1 = encode(c, k=1, mode=mode, safe=True)
    assert is_true(f0) is True
    assert is_true(f1) is False
    # reach-bad at k: s_1=1 → bad_1 holds → TRUE; s_0=0 → bad_0 fails → FALSE.
    g0 = encode(c, k=0, mode=mode, safe=False)
    g1 = encode(c, k=1, mode=mode, safe=False)
    assert is_true(g0) is False
    assert is_true(g1) is True


def test_copy_input_unrolled_safe() -> None:
    """∀i. ¬bad: s_1=i_0; bad_1=s_1=i_0. Fails when i_0=1 → FALSE for k≥1."""
    c = parse_seq_aag(COPY_INPUT)
    assert is_true(encode(c, k=0, mode="unrolled", safe=True)) is True
    assert is_true(encode(c, k=1, mode="unrolled", safe=True)) is False


def test_blackbox_makes_dqbf() -> None:
    """With bb, deps of bb-output are restricted to its input cone."""
    c = parse_seq_aag(WITH_BB)
    f = encode(c, k=1, blackboxes={6}, mode="unrolled", safe=True)
    # Find the bb existentials: those whose deps are a strict subset of all-inputs.
    all_u = set(f.universals)
    bb_vars = [y for y, d in f.dependencies.items() if d < all_u and len(d) <= 1]
    assert bb_vars, "expected at least one bb-output existential with restricted deps"
    # Semantically: bb≡0 keeps s=0 forever → safe. TRUE.
    assert is_true(f) is True


def test_blackbox_cannot_help() -> None:
    c = parse_seq_aag(WITH_BB_UNSAFE)
    f = encode(c, k=0, blackboxes={6}, mode="unrolled", safe=True)
    assert is_true(f) is False  # bad_0 = ¬s_0 = 1 regardless of bb


def test_unrolled_var_growth() -> None:
    c = parse_seq_aag(WITH_BB)
    f1 = encode(c, k=1, mode="unrolled")
    f3 = encode(c, k=3, mode="unrolled")
    assert f3.n_vars > f1.n_vars
    assert len(f3.universals) == 4 * len(c.inputs)  # k+1 copies


def test_succinct_T_once() -> None:
    """Succinct gate-clause count is independent of k."""
    c = parse_seq_aag(WITH_BB)
    n1 = len(encode(c, k=1, mode="succinct").clauses)
    n4 = len(encode(c, k=4, mode="succinct").clauses)
    # Only the per-step transition guards grow with k; gate Tseitin (3/gate) is constant.
    assert n4 - n1 <= 3 * 4 * len(c.latches) + 4  # loose bound; key: not O(k·|gates|)


def test_comment_header() -> None:
    c = parse_seq_aag(TOGGLE)
    f = encode(c, k=2, mode="unrolled", source="toggle.aag")
    assert any("pec2dqbf" in cm and "toggle.aag" in cm for cm in f.comments)
