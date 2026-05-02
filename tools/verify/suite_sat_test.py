"""SAT-certificate verification suite.

Each case is (id, dqdimacs, aag, expected) where expected ∈
{"valid", "invalid", "dep", "error"}. "valid" ⇔ the verification CNF is
UNSAT and there are no dep-violations; "invalid" ⇔ CNF is SAT (cert
fails the matrix); "dep" ⇔ dep_violations is non-empty (must NOT report
valid); "error" ⇔ parsing must raise. See THREATS.md.
"""

from __future__ import annotations

import pytest

from tools.verify.formats import parse_aag, parse_dqdimacs
from tools.verify.sat import encode_verification


def _brute_sat(n_vars: int, clauses: list[list[int]]) -> bool:
    if n_vars > 20:
        pytest.skip("CNF too large for brute force")
    for bits in range(1 << n_vars):
        a = {v + 1: bool(bits >> v & 1) for v in range(n_vars)}
        if all(any(a[abs(x)] == (x > 0) for x in c) for c in clauses):
            return True
    return False


def aag(m: int, inputs: list[int], outputs: list[int], gates: list[tuple], syms: str) -> str:
    h = f"aag {m} {len(inputs)} 0 {len(outputs)} {len(gates)}\n"
    body = "".join(f"{x}\n" for x in inputs)
    body += "".join(f"{x}\n" for x in outputs)
    body += "".join(f"{g} {a} {b}\n" for g, a, b in gates)
    return h + body + syms


# Common formula: ∀x1 x2. ∃y3(x1). ∃y4(x2). y3↔x1 ∧ y4↔x2  (SAT; cert: y3=x1,y4=x2)
F_COPY = "p cnf 4 4\na 1 2 0\nd 3 1 0\nd 4 2 0\n-1 3 0\n1 -3 0\n-2 4 0\n2 -4 0\n"
# ∀x1 x2. ∃y3(x1). y3↔x2 (UNSAT — every cert must be INVALID)
F_WRONGDEP = "p cnf 3 2\na 1 2 0\nd 3 1 0\n-2 3 0\n2 -3 0\n"
# ∀x1. ∃y2(x1). y2  (SAT; cert: y2=1)
F_TRUE2 = "p cnf 2 1\na 1 0\nd 2 1 0\n2 0\n"
# ∀x1. ∃y2(). y2↔x1  (UNSAT; y2 has empty deps)
F_NODEP = "p cnf 2 2\na 1 0\nd 2 0\n-1 2 0\n1 -2 0\n"
# ∀x1 x2. ∃y3(x1,x2). y3↔(x1∧x2)  (SAT)
F_AND3 = "p cnf 3 3\na 1 2 0\nd 3 1 2 0\n-3 1 0\n-3 2 0\n3 -1 -2 0\n"

# --- valid certs (encoding CNF must be UNSAT, no dep violations) ---------

VALID = [
    (
        "S-V1-identity",
        F_COPY,
        aag(2, [2, 4], [2, 4], [], "i0 u1\ni1 u2\no0 e3\no1 e4\n"),
    ),
    (
        "S-V2-const-true",
        F_TRUE2,
        aag(1, [2], [1], [], "i0 u1\no0 e2\n"),
    ),
    (
        "S-V3-const-true-no-input-used",
        F_TRUE2,
        aag(0, [], [1], [], "o0 e2\n"),
    ),
    (
        "S-V4-and-gate",
        F_AND3,
        aag(3, [2, 4], [6], [(6, 2, 4)], "i0 u1\ni1 u2\no0 e3\n"),
    ),
    (
        "S-V5-inverted-output",
        # ∃y2(x1). y2↔¬x1
        "p cnf 2 2\na 1 0\nd 2 1 0\n1 2 0\n-1 -2 0\n",
        aag(1, [2], [3], [], "i0 u1\no0 e2\n"),  # output = ¬input
    ),
    (
        "S-V6-shared-output",
        # y3=y4=x1; both deps allow x1.
        "p cnf 4 2\na 1 2 0\nd 3 1 0\nd 4 1 2 0\n-1 3 0\n-1 4 0\n",
        aag(2, [2, 4], [2, 2], [], "i0 u1\ni1 u2\no0 e3\no1 e4\n"),
    ),
    (
        "S-V7-subset-deps",
        # y3 may depend on {x1,x2} but cert uses only x1.
        "p cnf 3 2\na 1 2 0\nd 3 1 2 0\n-1 3 0\n1 -3 0\n",
        aag(2, [2, 4], [2], [], "i0 u1\ni1 u2\no0 e3\n"),
    ),
    (
        "S-V8-xor",
        # y3 = x1 XOR x2; deps {1,2}.
        "p cnf 3 4\na 1 2 0\nd 3 1 2 0\n-1 -2 -3 0\n-1 2 3 0\n1 -2 3 0\n1 2 -3 0\n",
        # XOR via gates: g6=x1&x2, g8=¬x1&¬x2, g10=¬g6&¬g8, out=g10? No: XOR = (a|b)&¬(a&b)
        # Simpler: a⊕b = ¬(¬(a&¬b)&¬(¬a&b)) = OR of two ANDs.
        # g6=a&¬b (2,5), g8=¬a&b (3,4), out = ¬(¬g6 & ¬g8) = g10 inverted where g10=¬g6&¬g8
        aag(
            5,
            [2, 4],
            [11],
            [(6, 2, 5), (8, 3, 4), (10, 7, 9)],
            "i0 u1\ni1 u2\no0 e3\n",
        ),
    ),
    (
        "S-V9-tautological-matrix",
        "p cnf 2 1\na 1 0\nd 2 1 0\n1 -1 0\n",
        aag(1, [2], [0], [], "i0 u1\no0 e2\n"),  # any cert works
    ),
    (
        "S-V10-no-clauses",
        "p cnf 2 0\na 1 0\nd 2 1 0\n",
        aag(1, [2], [0], [], "i0 u1\no0 e2\n"),
    ),
    (
        "S-V11-no-existentials",
        "p cnf 1 1\na 1 0\n1 -1 0\n",
        aag(1, [2], [], [], "i0 u1\n"),  # nothing to certify
    ),
    (
        "S-V12-propositional",
        "p cnf 1 1\ne 1 0\n1 0\n",
        aag(0, [], [1], [], "o0 e1\n"),  # y1=true, no universals
    ),
    (
        "S-V13-gate-chain",
        F_AND3,
        # y3 = ((x1&1)&x2) — extra gate, same function
        aag(4, [2, 4], [8], [(6, 2, 1), (8, 6, 4)], "i0 u1\ni1 u2\no0 e3\n"),
    ),
    (
        "S-V14-output-is-gate-of-inverted-inputs",
        # y2 = ¬x1 via gate: g=¬x1&¬x1=¬x1? No, g=¬x1&1, out=g.
        "p cnf 2 2\na 1 0\nd 2 1 0\n1 2 0\n-1 -2 0\n",
        aag(2, [2], [4], [(4, 3, 1)], "i0 u1\no0 e2\n"),
    ),
]

# --- dep violations (must populate dep_violations; never "valid") --------

DEP = [
    (
        "S-D1-direct-forbidden",
        F_COPY,
        # e3 wired to u2 (forbidden — dep(3)={1})
        aag(2, [2, 4], [4, 4], [], "i0 u1\ni1 u2\no0 e3\no1 e4\n"),
    ),
    (
        "S-D2-transitive-forbidden",
        F_COPY,
        # e3 = u1 & u2 (u2 forbidden via gate)
        aag(3, [2, 4], [6, 4], [(6, 2, 4)], "i0 u1\ni1 u2\no0 e3\no1 e4\n"),
    ),
    (
        "S-D11-inverted-forbidden",
        F_COPY,
        aag(2, [2, 4], [5, 4], [], "i0 u1\ni1 u2\no0 e3\no1 e4\n"),  # e3=¬u2
    ),
    (
        "S-D3-masked-by-const",
        F_COPY,
        # e3 = u2 & 0 = 0 — semantically constant, but cone touches u2.
        # Verifier is conservative: structural cone check should still flag it.
        aag(3, [2, 4], [6, 4], [(6, 4, 0)], "i0 u1\ni1 u2\no0 e3\no1 e4\n"),
    ),
    (
        "S-D4-unnamed-input",
        F_COPY,
        # input 4 has NO symbol-table entry; e3 uses it. Must be flagged on e3.
        aag(2, [2, 4], [4, 4], [], "i0 u1\no0 e3\no1 e4\n"),
    ),
    (
        "S-D4b-unnamed-input-only-dep",
        # e2 deps={1}; sole input is unnamed → must flag.
        F_TRUE2,
        aag(1, [2], [2], [], "o0 e2\n"),
    ),
    (
        "S-D5-misnamed-input",
        F_COPY,
        # input named "x2" instead of "u2" — must be treated as forbidden
        aag(2, [2, 4], [4, 2], [], "i0 u1\ni1 x2\no0 e3\no1 e4\n"),
    ),
    (
        "S-D6-input-not-a-universal",
        F_COPY,
        # input named u9 (no such universal) — must be forbidden
        aag(2, [2, 4], [4, 2], [], "i0 u1\ni1 u9\no0 e3\no1 e4\n"),
    ),
    (
        "S-D10-empty-deps-uses-input",
        F_NODEP,
        aag(1, [2], [2], [], "i0 u1\no0 e2\n"),
    ),
    (
        "S-O1-missing-output",
        F_COPY,
        aag(2, [2, 4], [2], [], "i0 u1\ni1 u2\no0 e3\n"),  # no e4
    ),
]

# --- semantically invalid certs (CNF must be SAT) ------------------------

INVALID = [
    (
        "S-E1-const-false",
        F_TRUE2,
        aag(1, [2], [0], [], "i0 u1\no0 e2\n"),  # y2=0 fails clause {y2}
    ),
    (
        "S-E2-swapped",
        F_COPY,
        # y3=x1 (ok), y4=x1 — wrong (y4 should be x2). But x1 ∉ dep(4)={2}!
        # This is BOTH a dep violation AND semantically wrong; counted under DEP above.
        # Here: y3=¬x1, y4=x2 — within deps but semantically wrong.
        aag(2, [2, 4], [3, 4], [], "i0 u1\ni1 u2\no0 e3\no1 e4\n"),
    ),
    (
        "S-E3-unsat-formula",
        F_WRONGDEP,
        # ANY cert is invalid (formula is UNSAT). y3=x1.
        aag(2, [2, 4], [2], [], "i0 u1\ni1 u2\no0 e3\n"),
    ),
    (
        "S-E3b-unsat-formula-const",
        F_WRONGDEP,
        aag(2, [2, 4], [1], [], "i0 u1\ni1 u2\no0 e3\n"),  # y3=1
    ),
    (
        "S-E3c-unsat-formula-const0",
        F_WRONGDEP,
        aag(2, [2, 4], [0], [], "i0 u1\ni1 u2\no0 e3\n"),  # y3=0
    ),
    (
        "S-E5-empty-clause",
        "p cnf 2 1\na 1 0\nd 2 1 0\n0\n",
        aag(1, [2], [1], [], "i0 u1\no0 e2\n"),
    ),
    (
        "S-E8-prop-wrong-const",
        "p cnf 1 1\ne 1 0\n1 0\n",
        aag(0, [], [0], [], "o0 e1\n"),  # y1=0 fails
    ),
    (
        "S-E11-and-wrong",
        F_AND3,
        # y3 = x1 OR x2 instead of AND — fails when x1=1,x2=0 (clause -3 1 fails)
        # OR via De Morgan: ¬(¬x1&¬x2) = inverted gate
        aag(3, [2, 4], [7], [(6, 3, 5)], "i0 u1\ni1 u2\no0 e3\n"),
    ),
    (
        "S-E12-nodep-const-true",
        F_NODEP,
        aag(1, [2], [1], [], "i0 u1\no0 e2\n"),  # y2=1 fails when x1=0
    ),
    (
        "S-E12b-nodep-const-false",
        F_NODEP,
        aag(1, [2], [0], [], "i0 u1\no0 e2\n"),  # y2=0 fails when x1=1
    ),
    (
        "S-E13-partially-correct",
        F_COPY,
        aag(2, [2, 4], [2, 5], [], "i0 u1\ni1 u2\no0 e3\no1 e4\n"),  # y3 ok, y4=¬x2 wrong
    ),
    (
        "S-E14-only-universals",
        # No existentials; matrix is x1 (not a tautology) — CNF must be SAT (x1=0).
        "p cnf 1 1\na 1 0\n1 0\n",
        aag(1, [2], [], [], "i0 u1\n"),
    ),
    (
        "S-E15-three-existentials-one-wrong",
        "p cnf 5 3\na 1 2 0\nd 3 1 0\nd 4 2 0\nd 5 1 2 0\n-1 3 0\n-2 4 0\n5 -1 -2 0\n",
        aag(3, [2, 4], [2, 4, 7], [(6, 2, 4)], "i0 u1\ni1 u2\no0 e3\no1 e4\no2 e5\n"),
    ),
    (
        "S-E16-double-negation-wrong",
        F_TRUE2,
        # output is ¬1 = 0 via two inversions? No: lit 1 IS true. ¬¬true=true. Use gate.
        # Actually: e2 should be 1; cert gives ¬(x1&¬x1)=1. Hmm that's valid.
        # Use: e2 = x1 & ¬x1 = 0. INVALID.
        aag(2, [2], [4], [(4, 2, 3)], "i0 u1\no0 e2\n"),
    ),
]

# --- parse errors --------------------------------------------------------

ERROR = [
    ("S-A1-latches", F_TRUE2, "aag 2 1 1 1 0\n2\n4 0\n2\ni0 u1\no0 e2\n"),
    ("S-A2-bad-header", F_TRUE2, "aig 1 1 0 1 0\n2\n2\n"),
    ("S-A2b-short-header", F_TRUE2, "aag 1 1 0\n"),
    ("S-A3-gate-lhs-odd", F_AND3, aag(3, [2, 4], [6], [(7, 2, 4)], "i0 u1\ni1 u2\no0 e3\n")),
    (
        "S-A4-gate-lhs-collides-input",
        F_AND3,
        aag(3, [2, 4], [2], [(2, 2, 4)], "i0 u1\ni1 u2\no0 e3\n"),
    ),
    (
        "S-A5-gate-operand-undefined",
        F_AND3,
        aag(3, [2, 4], [6], [(6, 2, 18)], "i0 u1\ni1 u2\no0 e3\n"),
    ),
    ("S-A6-output-undefined", F_TRUE2, aag(1, [2], [8], [], "i0 u1\no0 e2\n")),
    ("S-A7-empty", F_TRUE2, ""),
    (
        "S-A8-input-symbol-oob",
        F_TRUE2,
        aag(1, [2], [2], [], "i9 u1\no0 e2\n"),
    ),
    (
        "S-O4-output-symbol-oob",
        F_COPY,
        aag(2, [2, 4], [2, 4], [], "i0 u1\ni1 u2\no5 e3\no1 e4\n"),
    ),
    (
        "S-P1-undeclared-var-in-clause",
        "p cnf 2 1\na 1 0\nd 2 1 0\n2 9 0\n",
        aag(1, [2], [1], [], "i0 u1\no0 e2\n"),
    ),
]

# --- the parametrized tests ----------------------------------------------


@pytest.mark.parametrize("name,dqd,cert", VALID, ids=[c[0] for c in VALID])
def test_valid_certs(name: str, dqd: str, cert: str) -> None:
    enc = encode_verification(parse_dqdimacs(dqd), parse_aag(cert))
    assert enc.dep_violations == [], f"{name}: spurious dep-violation {enc.dep_violations}"
    assert _brute_sat(enc.n_vars, enc.clauses) is False, f"{name}: valid cert REJECTED"


@pytest.mark.parametrize("name,dqd,cert", DEP, ids=[c[0] for c in DEP])
def test_dep_violations(name: str, dqd: str, cert: str) -> None:
    enc = encode_verification(parse_dqdimacs(dqd), parse_aag(cert))
    assert enc.dep_violations, f"{name}: dependency/structural violation NOT detected"


@pytest.mark.parametrize("name,dqd,cert", INVALID, ids=[c[0] for c in INVALID])
def test_invalid_certs(name: str, dqd: str, cert: str) -> None:
    enc = encode_verification(parse_dqdimacs(dqd), parse_aag(cert))
    assert enc.dep_violations == [], (
        f"{name}: classified as dep-violation, expected semantic-invalid"
    )
    assert _brute_sat(enc.n_vars, enc.clauses) is True, f"{name}: invalid cert ACCEPTED as valid"


@pytest.mark.parametrize("name,dqd,cert", ERROR, ids=[c[0] for c in ERROR])
def test_parse_errors(name: str, dqd: str, cert: str) -> None:
    _ = name
    with pytest.raises((ValueError, KeyError, IndexError)):
        encode_verification(parse_dqdimacs(dqd), parse_aag(cert))


def test_case_counts() -> None:
    total = len(VALID) + len(DEP) + len(INVALID) + len(ERROR)
    assert len(VALID) >= 12
    assert len(DEP) >= 10
    assert len(INVALID) >= 10
    assert total >= 40, f"only {total} SAT cases"
