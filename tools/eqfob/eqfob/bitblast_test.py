from core.semantics import is_true
from tools.eqfob.eqfob.bitblast import bitblast
from tools.eqfob.eqfob.parse import parse
from tools.eqfob.eqfob.typecheck import check


def compile_text(src: str, **overrides):
    return bitblast(check(parse(src), overrides=overrides))


IDENTITY = """
param N = 1
fun f : bv[N] -> bv[N]
forall x : bv[N]
f(x) == x
"""

NEGATION = """
param N = 1
fun f : bv[N] -> bv[N]
forall x : bv[N]
f(x) == ~x
"""

CONTRADICTORY = """
param N = 1
fun f : bv[N] -> bv[N]
forall x : bv[N]
f(x) == x && f(x) == ~x
"""

NO_CONSTANT_INVERSE = """
exists z : bv[1]
forall x : bv[1]
x + z == 0
"""


def test_identity_sat() -> None:
    f = compile_text(IDENTITY)
    assert is_true(f) is True


def test_negation_sat() -> None:
    f = compile_text(NEGATION)
    assert is_true(f) is True


def test_contradictory_unsat() -> None:
    f = compile_text(CONTRADICTORY)
    assert is_true(f) is False


def test_no_constant_additive_inverse_unsat() -> None:
    f = compile_text(NO_CONSTANT_INVERSE)
    assert is_true(f) is False


def test_examples_compile() -> None:
    from pathlib import Path

    ex = Path(__file__).resolve().parents[1] / "examples"
    for name, ov in [("add_gt.eqfob", {"A": 2, "B": 2}), ("dep_cycle.eqfob", {"N": 1})]:
        f = compile_text((ex / name).read_text(), **ov)
        assert f.n_vars > 0 and len(f.clauses) > 0


def test_param_override() -> None:
    f1 = compile_text(IDENTITY, N=1)
    f3 = compile_text(IDENTITY, N=3)
    assert len(f3.universals) == 3 * len(f1.universals)


def test_ackermann_added_for_multiple_calls() -> None:
    # Structural: two call sites of f → Ackermann adds extra clauses beyond the
    # single-call case. (Semantic brute force doesn't scale here; CONTRADICTORY
    # already exercises same-arg congruence semantically.)
    one_call = compile_text("fun f: bv[1]->bv[1]\nforall a: bv[1]\nf(a)==a\n")
    two_calls = compile_text(
        "fun f: bv[1]->bv[1]\nforall a: bv[1]\nforall b: bv[1]\nf(a)==a\nf(b)==b\n"
    )
    assert len(two_calls.clauses) > 2 * len(one_call.clauses)
