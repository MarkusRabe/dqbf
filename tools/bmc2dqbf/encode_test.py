from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from core import dqdimacs
from core.formula import Formula
from core.semantics import is_true
from tools.bmc2dqbf.encode import encode, encode_succinct
from tools.pec2dqbf.aiger_seq import parse_seq_aag


def _find_hqs() -> Path | None:
    for p in (
        Path(__file__).resolve().parents[2] / "third_party/hqs/HQS/build/src/hqs/hqs2",
        Path("/root/home/opensrc/dqbf/third_party/hqs/HQS/build/src/hqs/hqs2"),
    ):
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


# --- succinct encoding ----------------------------------------------------


@pytest.mark.parametrize("aag", [TOGGLE, COPY_INPUT, COUNTER2])
@pytest.mark.parametrize("k", [0, 1, 2, 3, 4, 7])
def test_succinct_equisat_with_unrolled(aag: str, k: int) -> None:
    """encode_succinct(safe=False) ⟺ encode(safe=False) via hqs.

    The brute-force `is_true` oracle is exponential in the Skolem space,
    which is too large for the succinct encoding (every signal is an
    ∃-function). Use a real DQBF solver instead.
    """
    c = parse_seq_aag(aag)
    ref = _hqs_solve(encode(c, k=k))
    got = _hqs_solve(encode_succinct(c, k=k))
    assert got is not None and got == ref, f"k={k}: succinct={got} unrolled={ref}"


def test_succinct_is_dqbf() -> None:
    """The two index copies have incomparable dep sets → genuine DQBF."""
    c = parse_seq_aag(COUNTER2)
    f = encode_succinct(c, k=7)
    m = len(f.universals) // 2
    dt = frozenset(f.universals[:m])
    dtp = frozenset(f.universals[m:])
    assert any(d == dt for d in f.dependencies.values())
    assert any(d == dtp for d in f.dependencies.values())
    assert not (dt <= dtp or dtp <= dt)


def test_succinct_size_vs_unrolled() -> None:
    """Succinct n_vars stays bounded as k grows; unrolled is linear in k."""
    c = parse_seq_aag(COUNTER2)
    u8, u64 = encode(c, k=8), encode(c, k=64)
    s8, s64 = encode_succinct(c, k=8), encode_succinct(c, k=64)
    assert u64.n_vars > 6 * u8.n_vars  # ≈ linear
    assert s64.n_vars < 2 * s8.n_vars  # ≈ logarithmic
    assert s64.n_vars < u64.n_vars


def test_succinct_safe_raises() -> None:
    c = parse_seq_aag(TOGGLE)
    with pytest.raises(NotImplementedError):
        encode_succinct(c, k=2, safe=True)


def test_succinct_comment_header() -> None:
    c = parse_seq_aag(TOGGLE)
    f = encode_succinct(c, k=5, source="toggle.aag")
    assert any("encode_succinct" in cm and "toggle.aag" in cm for cm in f.comments)
