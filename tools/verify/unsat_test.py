"""Tests for the self-contained UNSAT proof checker.

These exercise `verify_proof` directly with hand-built traces — no
prover involved.
"""

from core.formula import make_formula
from core.proof_trace import Proof
from tools.verify.unsat import verify_proof


def test_simple_res_refutation() -> None:
    f = make_formula(universals=[], dependencies={1: []}, clauses=[[1], [-1]])
    p = Proof()
    p.add(clause=(1,), rule="axiom")
    p.add(clause=(-1,), rule="axiom")
    p.add(clause=(), rule="res", premises=(0, 1), pivot=1)
    assert verify_proof(f, p)


def test_fex_sibling_pair_replays() -> None:
    """Regression: both FEx halves with the same fresh id replay."""
    f = make_formula(
        universals=[1, 2],
        dependencies={3: [1], 4: [2]},
        clauses=[[3, 4], [-3], [-4]],
    )
    p = Proof()
    p.add(clause=(3, 4), rule="axiom")
    p.add(clause=(-3,), rule="axiom")
    p.add(clause=(-4,), rule="axiom")
    p.add(clause=(3, 5), rule="fex", premises=(0,), part=(3,), fresh=5)
    p.add(clause=(-5, 4), rule="fex", premises=(0,), part=(3,), fresh=5)
    p.add(clause=(5,), rule="res", premises=(3, 1), pivot=3)
    p.add(clause=(-5,), rule="res", premises=(4, 2), pivot=4)
    p.add(clause=(), rule="res", premises=(5, 6), pivot=5)
    assert verify_proof(f, p)


def test_rejects_non_axiom_clause() -> None:
    f = make_formula(universals=[], dependencies={1: []}, clauses=[[1]])
    p = Proof()
    p.add(clause=(-1,), rule="axiom")  # not in f
    assert not verify_proof(f, p)


def test_rejects_wrong_resolvent() -> None:
    f = make_formula(universals=[], dependencies={1: [], 2: []}, clauses=[[1, 2], [-1]])
    p = Proof()
    p.add(clause=(1, 2), rule="axiom")
    p.add(clause=(-1,), rule="axiom")
    p.add(clause=(1,), rule="res", premises=(0, 1), pivot=1)  # wrong (should be {2})
    assert not verify_proof(f, p)


def test_rejects_unknown_rule() -> None:
    f = make_formula(universals=[], dependencies={1: []}, clauses=[[1]])
    p = Proof()
    p.add(clause=(1,), rule="bogus")
    assert not verify_proof(f, p)
