"""End-to-end: prover → on-disk certificates → independent verifier.

The verifier is exercised through its **file** interface (DQDIMACS,
.frp, .aag) — the only contract it shares with provers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import dqdimacs
from core.aiger import skolem_to_aag
from core.proof_trace import save as save_proof
from provers.forkres.search import Result, SearchConfig, solve
from tools.verify.formats import load_aag, load_dqdimacs, load_proof
from tools.verify.sat import encode_verification
from tools.verify.unsat import verify_proof

HERE = Path(__file__).parent
MANIFEST = json.loads((HERE / "manifest.json").read_text())
CFG = SearchConfig(timeout_s=1.0, max_clauses=2000, max_forks=16)


@pytest.mark.integration
@pytest.mark.parametrize("entry", MANIFEST, ids=lambda e: e["path"])
def test_forkres_e2e(entry: dict, tmp_path: Path) -> None:
    src = HERE / entry["path"]
    f = dqdimacs.load(src)
    out = solve(f, CFG)
    expected = entry["expected"]
    vf = load_dqdimacs(src)

    if expected == "sat":
        assert out.result is Result.SAT, out.log
        assert out.skolem is not None
        aag_path = tmp_path / "cert.aag"
        aag_path.write_text(skolem_to_aag(f, out.skolem))
        enc = encode_verification(vf, load_aag(aag_path))
        assert enc.dep_violations == []
        assert _brute_unsat(enc.n_vars, enc.clauses), "verification CNF must be UNSAT"
    elif expected == "unsat":
        assert out.result is Result.UNSAT, out.log
        assert out.proof is not None
        frp = tmp_path / "proof.frp"
        save_proof(frp, out.proof)
        assert verify_proof(vf, load_proof(frp))
    else:
        pytest.fail(f"unknown expected={expected!r}")


def _brute_unsat(n_vars: int, clauses: list[list[int]]) -> bool:
    if n_vars > 20:
        pytest.skip("verification CNF too large for brute-force")
    for bits in range(1 << n_vars):
        a = {v + 1: bool(bits >> v & 1) for v in range(n_vars)}
        if all(any(a[abs(x)] == (x > 0) for x in c) for c in clauses):
            return False
    return True
