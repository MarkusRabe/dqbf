"""Tests for the SAT-certificate verifier.

Uses inline `.aag` strings and `tools.verify.formats` only.
"""

from tools.verify.formats import Formula, parse_aag
from tools.verify.sat import decode_model, encode_verification, solve_cnf


def _f(universals, deps, clauses) -> Formula:
    return Formula(
        n_vars=max([*universals, *deps, *(abs(x) for c in clauses for x in c)], default=0),
        universals=tuple(universals),
        dependencies={y: frozenset(d) for y, d in deps.items()},
        clauses=tuple(frozenset(c) for c in clauses),
    )


def _brute_sat(n_vars: int, clauses: list[list[int]]) -> bool:
    assert n_vars <= 16
    for bits in range(1 << n_vars):
        a = {v + 1: bool(bits >> v & 1) for v in range(n_vars)}
        if all(any(a[abs(x)] == (x > 0) for x in c) for c in clauses):
            return True
    return False


# AIG: inputs u1,u2; e3 = u1, e4 = u2 (identity).
AAG_ID = """\
aag 4 2 0 2 2
2
4
6
8
6 2 2
8 4 4
i0 u1
i1 u2
o0 e3
o1 e4
"""

# AIG: e3 = ¬u1 (inverted), e4 = u2.
AAG_BAD = """\
aag 4 2 0 2 2
2
4
7
8
6 2 2
8 4 4
i0 u1
i1 u2
o0 e3
o1 e4
"""

F_COPY = _f([1, 2], {3: [1], 4: [2]}, [[-1, 3], [1, -3], [-2, 4], [2, -4]])


def test_valid_cert_yields_unsat_cnf() -> None:
    enc = encode_verification(F_COPY, parse_aag(AAG_ID))
    assert enc.dep_violations == []
    assert _brute_sat(enc.n_vars, enc.clauses) is False


def test_invalid_cert_yields_sat_cnf() -> None:
    enc = encode_verification(F_COPY, parse_aag(AAG_BAD))
    assert _brute_sat(enc.n_vars, enc.clauses) is True


def test_dependency_violation_detected() -> None:
    f = _f([1, 2], {3: [1]}, [[3]])
    aag = "aag 2 2 0 1 0\n2\n4\n4\ni0 u1\ni1 u2\no0 e3\n"
    enc = encode_verification(f, parse_aag(aag))
    assert any("e3" in v and "2" in v for v in enc.dep_violations)


def test_missing_output_reported() -> None:
    f = _f([1], {2: [1]}, [[2]])
    aag = "aag 1 1 0 0 0\n2\ni0 u1\n"
    enc = encode_verification(f, parse_aag(aag))
    assert any("e2" in v and "no AIGER output" in v for v in enc.dep_violations)


def test_varmap_contents() -> None:
    enc = encode_verification(F_COPY, parse_aag(AAG_ID))
    assert "1" in enc.varmap["universals"]
    assert "3" in enc.varmap["existentials"]
    assert "0" in enc.varmap["violated_clause"]


def test_solve_cnf_backend_or_fallback() -> None:
    is_sat, _ = solve_cnf(2, [[1, 2], [-1], [-2]])
    if is_sat is None:
        assert _brute_sat(2, [[1, 2], [-1], [-2]]) is False
    else:
        assert is_sat is False
    is_sat2, model2 = solve_cnf(2, [[1], [2]])
    if is_sat2 is None:
        assert _brute_sat(2, [[1], [2]]) is True
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
