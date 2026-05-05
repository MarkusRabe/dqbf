from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from core import dqdimacs
from core.formula import Formula
from core.semantics import is_true
from tools.bmc2dqbf.circuits import circuit_fifo1, circuit_mutex
from tools.bmc2dqbf.encode import encode
from tools.hwmc2dqbf_indinv.circuits_buggy import (
    circuit_alu_add_buggy,
    circuit_fifo1_buggy,
    circuit_mutex_buggy,
)
from tools.hwmc2dqbf_indinv.encode import Transition, encode_indinv, encode_indinv_aig
from tools.pec2dqbf.aiger_seq import parse_seq_aag


def _find_hqs() -> Path | None:
    p = Path(__file__).resolve().parents[2] / "third_party/hqs/HQS/build/src/hqs/hqs2"
    if p.exists():
        return p
    w = shutil.which("hqs2")
    return Path(w) if w else None


_HQS = _find_hqs()


def _hqs_solve(f: Formula) -> bool | None:
    if _HQS is None:
        pytest.skip("hqs2 not available")
    with tempfile.NamedTemporaryFile("w", suffix=".dqdimacs", delete=False) as tf:
        tf.write(dqdimacs.dumps(f))
        tmp = tf.name
    cp = subprocess.run([str(_HQS), tmp], capture_output=True, text=True, timeout=30)
    Path(tmp).unlink(missing_ok=True)
    if cp.returncode == 10:
        return True
    if cp.returncode == 20:
        return False
    return None


# 1 latch s (lit 2), no inputs. next = ¬s. bad = s. Reset 0.  Reaches bad at step 1.
TOGGLE = "aag 1 0 1 1 0\n2 3\n2\n"

# 1 latch s, no inputs. next = s. bad = s. Reset 0.  Stuck at 0; bad unreachable.
STUCK0 = "aag 1 0 1 1 0\n2 2\n2\n"

# 2-bit counter (wraps): bad = l0∧l1. Reachable at step 3.
COUNTER2 = "aag 5 0 2 1 3\n2 3\n4 10\n6\n6 2 4\n8 3 5\n10 7 9\n"


def test_stuck0_has_invariant() -> None:
    """s'=s, reset=0, bad=s. Invariant Inv(s)=¬s works."""
    assert _hqs_solve(encode_indinv_aig(parse_seq_aag(STUCK0))) is True


def test_toggle_no_invariant() -> None:
    """s'=¬s, reset=0, bad=s. Reachable at step 1 ⇒ no Inv ⇒ UNSAT."""
    assert _hqs_solve(encode_indinv_aig(parse_seq_aag(TOGGLE))) is False


def test_counter2_no_invariant() -> None:
    """bad reachable ⇒ UNSAT."""
    assert _hqs_solve(encode_indinv_aig(parse_seq_aag(COUNTER2))) is False


def test_consistency_forces_same_function() -> None:
    """The {s},{s'} dep-sets are incomparable and the consistency clause
    is present, so the encoding is genuine DQBF."""
    f = encode_indinv_aig(parse_seq_aag(COUNTER2))
    nL = 2
    ds = frozenset(f.universals[:nL])
    dsp = frozenset(f.universals[-nL:])
    assert any(d == ds for d in f.dependencies.values())
    assert any(d == dsp for d in f.dependencies.values())
    assert not (ds <= dsp or dsp <= ds)


def test_mutex_safe_vs_buggy_hqs() -> None:
    """mutex n=2: original is safe (SAT), buggy is unsafe (UNSAT)."""
    safe, _ = circuit_mutex(2)
    bug, _ = circuit_mutex_buggy(2)
    assert _hqs_solve(encode_indinv_aig(parse_seq_aag(safe))) is True
    assert _hqs_solve(encode_indinv_aig(parse_seq_aag(bug))) is False


def test_fifo1_safe_vs_buggy_hqs() -> None:
    safe, _ = circuit_fifo1(2)
    bug, _ = circuit_fifo1_buggy(2)
    assert _hqs_solve(encode_indinv_aig(parse_seq_aag(safe))) is True
    assert _hqs_solve(encode_indinv_aig(parse_seq_aag(bug))) is False


def test_alu_add_buggy_hqs() -> None:
    bug, _ = circuit_alu_add_buggy(2)
    assert _hqs_solve(encode_indinv_aig(parse_seq_aag(bug))) is False


def test_buggy_is_reachable_via_bmc() -> None:
    """Cross-check: each buggy circuit reaches bad within k=2 in plain BMC."""
    for fn in (circuit_mutex_buggy, circuit_fifo1_buggy, circuit_alu_add_buggy):
        aag, _ = fn(2)
        c = parse_seq_aag(aag)
        assert _hqs_solve(encode(c, k=2)) is True, fn.__name__


def test_generic_transition_interface() -> None:
    """Backend-agnostic path: build a Transition by hand (s'=s, bad=s,
    init=¬s) and check SAT — this is STUCK0 without the AIGER frontend."""
    tr = Transition(
        n_vars=2,
        state=[1],
        inputs=[],
        next_state=[2],
        init=[-1],
        defs=[],
        trans=[[-2, 1], [2, -1]],
        bad=1,
    )
    assert is_true(encode_indinv(tr), budget=50_000_000) is True
    # Now bad always reachable (s'=1 always): UNSAT.
    tr2 = Transition(
        n_vars=2,
        state=[1],
        inputs=[],
        next_state=[2],
        init=[-1],
        defs=[],
        trans=[[2]],
        bad=1,
    )
    assert is_true(encode_indinv(tr2), budget=50_000_000) is False


def test_comment_header() -> None:
    f = encode_indinv_aig(parse_seq_aag(STUCK0), source="stuck0.aag")
    assert any("hwmc2dqbf_indinv" in c and "stuck0.aag" in c for c in f.comments)
    assert any("SAT = inductive invariant exists" in c for c in f.comments)
