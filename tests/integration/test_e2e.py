"""End-to-end: prover → result matches manifest → certificate verifies."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import dqdimacs
from provers.forkres.proof import replay
from provers.forkres.search import Result, SearchConfig, solve
from tools.verify.sat import verify_skolem

HERE = Path(__file__).parent
MANIFEST = json.loads((HERE / "manifest.json").read_text())
CFG = SearchConfig(timeout_s=1.0, max_clauses=2000, max_forks=16)


@pytest.mark.integration
@pytest.mark.parametrize("entry", MANIFEST, ids=lambda e: e["path"])
def test_forkres_e2e(entry: dict) -> None:
    f = dqdimacs.load(HERE / entry["path"])
    out = solve(f, CFG)
    expected = entry["expected"]
    if expected == "sat":
        assert out.result is Result.SAT, out.log
        assert out.skolem is not None and verify_skolem(f, out.skolem)
    elif expected == "unsat":
        assert out.result is Result.UNSAT, out.log
        assert out.proof is not None and replay(f, out.proof)
    else:
        pytest.fail(f"unknown expected={expected!r}")
