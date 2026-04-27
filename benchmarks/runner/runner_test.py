from pathlib import Path

from benchmarks.runner.manifest import Instance, load_family
from benchmarks.runner.report import summarize
from benchmarks.runner.run import _classify, run_one

TINY = Path(__file__).resolve().parents[2] / "tests" / "integration" / "tiny"


def test_classify() -> None:
    assert _classify("sat", "sat") == "ok"
    assert _classify("sat", "unsat") == "wrong"
    assert _classify("unknown", "sat") == "ok"
    assert _classify("sat", "unknown") == "unknown"
    assert _classify("sat", "timeout") == "timeout"


def test_load_family_infers_from_filename() -> None:
    insts = load_family("holdout/dqbf/qbfeval")
    if not insts:
        return
    assert any(i.expected == "unsat" for i in insts)


def test_run_one_against_stub() -> None:
    # Use the python interpreter as a "prover" that always exits 10.
    import sys

    inst = Instance(path=TINY / "copy_sat.dqdimacs", expected="sat", family="tiny")
    r = run_one(inst, [sys.executable, "-c", "import sys; sys.exit(10)", "--"], timeout_s=5.0)
    assert r.got == "sat"
    assert r.status == "ok"


def test_summarize() -> None:
    results = [
        {"family": "a", "status": "ok", "wall_s": 0.1},
        {"family": "a", "status": "wrong", "wall_s": 0.2},
        {"family": "b", "status": "unknown", "wall_s": 0.3},
    ]
    s = summarize(results)
    assert "a" in s and "b" in s
    assert " 1 " in s.splitlines()[2]
