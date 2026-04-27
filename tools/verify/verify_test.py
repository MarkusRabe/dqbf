from core.aiger import skolem_to_aag
from core.certificate import skolem_from_json, skolem_to_json
from core.formula import make_formula
from core.semantics import find_skolem
from provers.forkres.proof import Proof, replay
from provers.forkres.search import Result, SearchConfig, solve
from tools.verify.sat import verify_skolem
from tools.verify.unsat import verify_proof

CFG = SearchConfig(timeout_s=1.0)


def test_verify_skolem_roundtrip() -> None:
    f = make_formula(
        universals=[1, 2],
        dependencies={3: [1], 4: [2]},
        clauses=[[-1, 3], [1, -3], [-2, 4], [2, -4]],
    )
    sk = find_skolem(f)
    assert sk is not None
    assert verify_skolem(f, sk)
    sk2 = skolem_from_json(skolem_to_json(f, sk))
    assert verify_skolem(f, sk2)


def test_verify_skolem_rejects_incomplete() -> None:
    f = make_formula(universals=[1], dependencies={2: [1]}, clauses=[[2]])
    incomplete: dict[int, dict[tuple[bool, ...], bool]] = {2: {(False,): True}}
    assert verify_skolem(f, incomplete) is False


def test_verify_skolem_rejects_wrong() -> None:
    f = make_formula(
        universals=[1, 2],
        dependencies={3: [1], 4: [2]},
        clauses=[[-1, 3], [1, -3], [-2, 4], [2, -4]],
    )
    bad: dict[int, dict[tuple[bool, ...], bool]] = {
        3: {(False,): True, (True,): False},
        4: {(False,): False, (True,): True},
    }
    assert verify_skolem(f, bad) is False


def test_verify_proof_end_to_end() -> None:
    f = make_formula(universals=[1, 2], dependencies={3: [1]}, clauses=[[-2, 3], [2, -3]])
    out = solve(f, CFG)
    assert out.result is Result.UNSAT and out.proof is not None
    assert verify_proof(f, out.proof)
    s = out.proof.dumps()
    assert replay(f, Proof.loads(s))


def test_aag_writer_produces_valid_header() -> None:
    f = make_formula(universals=[1, 2], dependencies={3: [1], 4: [2]}, clauses=[[-1, 3]])
    sk: dict[int, dict[tuple[bool, ...], bool]] = {
        3: {(False,): False, (True,): True},
        4: {(False,): True, (True,): False},
    }
    aag = skolem_to_aag(f, sk)
    assert aag.startswith("aag ")
    lines = aag.strip().splitlines()
    hdr = lines[0].split()
    assert hdr[0] == "aag" and hdr[3] == "0"  # combinational
    assert any(ln.startswith("o0 e3") for ln in lines)
