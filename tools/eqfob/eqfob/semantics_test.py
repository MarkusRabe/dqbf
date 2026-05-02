"""Semantic tests for EQFOB: compile → brute-force `core.semantics.is_true`.

Widths are kept tiny (mostly bv[1]) so the Skolem-enumeration oracle
terminates — every Tseitin auxiliary is itself an existential, so the
search space is the product of 2^(2^|deps|) over *all* of them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.semantics import is_true
from tools.eqfob.eqfob.bitblast import bitblast
from tools.eqfob.eqfob.parse import parse
from tools.eqfob.eqfob.typecheck import check

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def compile_text(src: str, **overrides):
    return bitblast(check(parse(src), overrides=overrides))


def compile_file(name: str, **overrides):
    return compile_text((EXAMPLES / name).read_text(), **overrides)


# --- conditionals ---------------------------------------------------------


def test_ite_with_function() -> None:
    # ∃f. ∀x. f(x) = ite(x==1, x, ~x)  — SAT (f ≡ const 1; both branches typed by x).
    src = "fun f:bv[1]->bv[1]\nforall x:bv[1]\nf(x) == ite(x==1, x, ~x)\n"
    assert is_true(compile_text(src)) is True


def test_ite_condition_selects() -> None:
    # Tautology: ite(true, x, ~x) == x
    src = "forall x:bv[1]\nite(x==x, x, ~x) == x\n"
    assert is_true(compile_text(src)) is True


# --- Ackermann congruence -------------------------------------------------


def test_ackermann_same_arg_unsat() -> None:
    # f(x) ≠ f(x) is UNSAT — congruence forces the two call sites to agree.
    assert is_true(compile_file("ackermann_neq.eqfob")) is False


def test_ackermann_distinct_args_sat() -> None:
    # f(0) ≠ f(1) is SAT — distinct args, congruence is vacuous, pick f=id.
    src = "fun f:bv[1]->bv[1]\nf(0) != f(1)\n"
    assert is_true(compile_text(src)) is True


# --- extract / zext / sext -----------------------------------------------


def test_extract_low_sat() -> None:
    assert is_true(compile_file("extract_low.eqfob", N=2)) is True


def test_zext_bound_tautology() -> None:
    assert is_true(compile_file("zext_bound.eqfob")) is True


def test_sext_replicates_msb() -> None:
    # extract[1:1](sext[1](x)) == x for x:bv[1] — sign bit is replicated.
    src = "forall x:bv[1]\nextract[1:1](sext[1](x)) == x\n"
    assert is_true(compile_text(src)) is True


# --- boolean / bitwise / comparison corner cases -------------------------


def test_bv1_is_exhaustively_0_or_1() -> None:
    src = "forall x:bv[1]\n(x==0) || (x==1)\n"
    assert is_true(compile_text(src)) is True


def test_double_bvnot_is_identity() -> None:
    src = "forall x:bv[1]\n~(~x) == x\n"
    assert is_true(compile_text(src)) is True


def test_impl_and_iff() -> None:
    # (x -> x) && (x <-> x) — tautology exercising both bool binops.
    src = "forall x:bv[1]\n(x==1 -> x==1) && (x==1 <-> x==1)\n"
    assert is_true(compile_text(src)) is True


# --- UNSAT corner cases ---------------------------------------------------


def test_constant_cannot_track_universal() -> None:
    # ∃z. ∀x. z == x  — UNSAT (z has empty deps, can't equal both 0 and 1).
    src = "exists z:bv[1]\nforall x:bv[1]\nz == x\n"
    assert is_true(compile_text(src)) is False


def test_overconstrained_function() -> None:
    # ∃f. ∀x. f(x)=x ∧ f(x)=¬x  — UNSAT (also exercises congruence).
    src = "fun f:bv[1]->bv[1]\nforall x:bv[1]\nf(x)==x\nf(x)==~x\n"
    assert is_true(compile_text(src)) is False


# --- example files all compile (heavier ones: structure-only) ------------

ALL_EXAMPLES = [
    ("ite_max.eqfob", {"N": 1}),
    ("ackermann_neq.eqfob", {}),
    ("extract_low.eqfob", {"N": 2}),
    ("zext_bound.eqfob", {}),
    ("add_gt.eqfob", {"A": 2, "B": 2}),
    ("dep_cycle.eqfob", {"N": 1}),
]


@pytest.mark.parametrize("name,ov", ALL_EXAMPLES, ids=[n for n, _ in ALL_EXAMPLES])
def test_examples_compile(name: str, ov: dict[str, int]) -> None:
    f = compile_file(name, **ov)
    assert f.n_vars > 0 and len(f.clauses) > 0
