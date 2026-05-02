"""Cross-cutting test: prover output passes the independent verifier.

This test file MAY import from `provers/` because its purpose is to
check that prover output is accepted by `tools/verify/`. Production
verifier code (sat.py, unsat.py, cli.py) does not import `provers/`;
the boundary is enforced by `boundary_test.py`.
"""

from core.formula import make_formula
from core.proof_trace import Proof
from provers.forkres.search import Result, SearchConfig, solve
from tools.verify.unsat import verify_proof

CFG = SearchConfig(timeout_s=1.0)


def test_prover_unsat_proof_verifies() -> None:
    f = make_formula(universals=[1, 2], dependencies={3: [1]}, clauses=[[-2, 3], [2, -3]])
    out = solve(f, CFG)
    assert out.result is Result.UNSAT and out.proof is not None
    assert verify_proof(f, out.proof)
    assert verify_proof(f, Proof.loads(out.proof.dumps()))
