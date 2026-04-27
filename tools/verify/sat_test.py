from core.aiger import parse_aag, skolem_to_aag
from core.formula import make_formula
from core.semantics import find_skolem
from tools.verify.sat import decode_model, encode_verification, solve_cnf


def _solve_cnf(n_vars: int, clauses: list[list[int]]) -> bool:
    """Tiny brute-force SAT for test-sized CNFs (≤16 vars)."""
    assert n_vars <= 16
    for bits in range(1 << n_vars):
        a = {v + 1: bool(bits >> v & 1) for v in range(n_vars)}
        if all(any(a[abs(x)] == (x > 0) for x in c) for c in clauses):
            return True
    return False


def test_valid_cert_yields_unsat_cnf() -> None:
    f = make_formula(
        universals=[1, 2],
        dependencies={3: [1], 4: [2]},
        clauses=[[-1, 3], [1, -3], [-2, 4], [2, -4]],
    )
    sk = find_skolem(f)
    assert sk is not None
    aig = parse_aag(skolem_to_aag(f, sk))
    enc = encode_verification(f, aig)
    assert enc.dep_violations == []
    assert _solve_cnf(enc.n_vars, enc.clauses) is False  # UNSAT => cert valid


def test_invalid_cert_yields_sat_cnf() -> None:
    f = make_formula(
        universals=[1, 2],
        dependencies={3: [1], 4: [2]},
        clauses=[[-1, 3], [1, -3], [-2, 4], [2, -4]],
    )
    bad_sk: dict[int, dict[tuple[bool, ...], bool]] = {
        3: {(False,): True, (True,): False},  # y3 = ¬x1 (wrong)
        4: {(False,): False, (True,): True},
    }
    aig = parse_aag(skolem_to_aag(f, bad_sk))
    enc = encode_verification(f, aig)
    assert _solve_cnf(enc.n_vars, enc.clauses) is True  # SAT => cert invalid


def test_dependency_violation_detected() -> None:
    f = make_formula(universals=[1, 2], dependencies={3: [1]}, clauses=[[3]])
    # AIG where e3 depends on u2 (forbidden)
    aag = "aag 2 2 0 1 0\n2\n4\n4\ni0 u1\ni1 u2\no0 e3\n"
    enc = encode_verification(f, parse_aag(aag))
    assert any("e3" in v and "2" in v for v in enc.dep_violations)


def test_solve_cnf_backend_or_fallback() -> None:
    is_sat, _ = solve_cnf(2, [[1, 2], [-1], [-2]])
    if is_sat is None:
        assert _solve_cnf(2, [[1, 2], [-1], [-2]]) is False
    else:
        assert is_sat is False
    is_sat2, model2 = solve_cnf(2, [[1], [2]])
    if is_sat2 is None:
        assert _solve_cnf(2, [[1], [2]]) is True
    else:
        assert is_sat2 is True and model2 is not None and 1 in model2 and 2 in model2


def test_decode_model() -> None:
    varmap = {
        "universals": {"1": 1, "2": 2},
        "violated_clause": {"0": 3, "1": 4},
        "existentials": {},
        "aiger_gates": {},
        "TRUE": {"const": 5},
    }
    cex = decode_model([1, -2, 3, -4, 5], varmap)
    assert cex["universals"] == {"1": True, "2": False}
    assert cex["violated_clauses"] == ["0"]


def test_varmap_contents() -> None:
    f = make_formula(universals=[1], dependencies={2: [1]}, clauses=[[2, -1]])
    sk: dict[int, dict[tuple[bool, ...], bool]] = {2: {(False,): True, (True,): True}}
    aig = parse_aag(skolem_to_aag(f, sk))
    enc = encode_verification(f, aig)
    assert "1" in enc.varmap["universals"]
    assert "2" in enc.varmap["existentials"]
    assert "0" in enc.varmap["violated_clause"]
