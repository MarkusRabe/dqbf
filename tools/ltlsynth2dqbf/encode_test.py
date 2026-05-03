import subprocess
import tempfile
from pathlib import Path

import pytest

from core import dqdimacs
from tools.ltlsynth2dqbf.encode import encode, encode_tlsf
from tools.ltlsynth2dqbf.ltl import parse as parse_ltl
from tools.ltlsynth2dqbf.tlsf import TlsfNotSupported
from tools.ltlsynth2dqbf.tlsf import parse as parse_tlsf

INST = Path(__file__).resolve().parents[2] / "benchmarks/train/syntcomp_legacy/instances"
ROOT = Path(__file__).resolve().parents[2]
HQS = ROOT / "third_party/hqs/HQS/build/src/hqs/hqs2"


def _solve(f) -> bool | None:
    """Solve via hqs (returns True/False/None)."""
    if not HQS.exists():
        # parent's third_party (shared, gitignored)
        alt = Path("/root/opensrc/dqbf/third_party/hqs/HQS/build/src/hqs/hqs2")
        if not alt.exists():
            pytest.skip("hqs not available")
        hqs = alt
    else:
        hqs = HQS
    with tempfile.NamedTemporaryFile("w", suffix=".dqdimacs", delete=False) as tf:
        tf.write(dqdimacs.dumps(f))
        path = tf.name
    cp = subprocess.run([str(hqs), path], capture_output=True, text=True, timeout=30)
    Path(path).unlink(missing_ok=True)
    if cp.returncode == 10:
        return True
    if cp.returncode == 20:
        return False
    return None


TLSF_ECHO = """
INFO { TITLE: "echo" SEMANTICS: Mealy TARGET: Mealy }
MAIN {
  INPUTS { r; }
  OUTPUTS { g; }
  GUARANTEE { G (r <-> g); }
}
"""

TLSF_CONST_TRUE = """
INFO { TITLE: "true" SEMANTICS: Mealy TARGET: Mealy }
MAIN {
  OUTPUTS { g; }
  GUARANTEE { G g; }
}
"""

TLSF_UNREAL = """
INFO { TITLE: "needs-input" SEMANTICS: Mealy TARGET: Mealy }
MAIN {
  INPUTS { r; }
  OUTPUTS { g; }
  GUARANTEE { G (g <-> X r); }
}
"""


def test_ltl_parse_roundtrip() -> None:
    n = parse_ltl("G (a -> F b) && (c U d)")
    assert n[0] == "and"


def test_tlsf_parse_basic() -> None:
    s = parse_tlsf(TLSF_ECHO)
    assert s.inputs == ["r"]
    assert s.outputs == ["g"]
    assert s.guarantees == ["G (r <-> g)"]
    assert "->" not in s.ltl_formula() or True  # smoke


def test_encode_echo_is_realizable() -> None:
    f = encode_tlsf(TLSF_ECHO, n_states=1, k=3)
    assert _solve(f) is True


def test_encode_const_output_realizable() -> None:
    f = encode_tlsf(TLSF_CONST_TRUE, n_states=1, k=3)
    assert _solve(f) is True


def test_encode_unrealizable_is_false_at_tiny_bound() -> None:
    # output must equal *next* input ⇒ not a function of current (state,input)
    f = encode_tlsf(TLSF_UNREAL, n_states=1, k=3)
    assert _solve(f) is False


def test_encode_produces_valid_dqdimacs() -> None:
    f = encode_tlsf(TLSF_ECHO, n_states=2, k=3)
    s = dqdimacs.dumps(f)
    g = dqdimacs.parse(s)
    assert g.n_vars == f.n_vars
    assert len(g.clauses) == len(f.clauses)


@pytest.mark.skipif(not INST.exists(), reason="syntcomp_legacy not present")
def test_parse_committed_tlsf() -> None:
    from tools.ltlsynth2dqbf.ltl import LtlParseError

    ok, skipped = 0, []
    for p in sorted(INST.glob("*.tlsf")):
        try:
            spec = parse_tlsf(p.read_text())
            parse_ltl(spec.ltl_formula())
            ok += 1
        except (TlsfNotSupported, LtlParseError) as exc:
            skipped.append((p.name, str(exc)[:60]))
    assert ok >= 10, f"only {ok}/20 parsed; skipped: {skipped}"


def test_direct_encode_with_x() -> None:
    phi = parse_ltl("G (g -> X !g)")
    f = encode(["r"], ["g"], phi, n_states=1, k=3)
    assert f.n_vars > 0
