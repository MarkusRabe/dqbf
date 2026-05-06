from core.semantics import is_true
from tools.eqfob.eqfob.bitblast import bitblast
from tools.eqfob.eqfob.parse import parse
from tools.eqfob.eqfob.typecheck import check
from tools.verify.sat import solve_cnf


def compile_text(src: str, **overrides):
    return bitblast(check(parse(src), overrides=overrides))


def prop_sat(src: str) -> bool:
    """Compile and solve as propositional CNF. Only valid when the source
    has no `forall` (|U|=0), so the DQBF degenerates to plain SAT — used
    for ops like `*` whose Tseitin auxiliaries blow past `is_true`'s
    Skolem-enumeration budget at any useful width."""
    f = compile_text(src)
    assert len(f.universals) == 0, "prop_sat requires no universals"
    sat, _ = solve_cnf(f.n_vars, [list(c) for c in f.clauses])
    return sat


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


def test_mul_matches_shift_add() -> None:
    # No x makes 3*x differ from (x<<1)+x ⇒ the negated witness is UNSAT.
    assert prop_sat("exists x : bv[4]\n(3 * x) != ((x << 1) + x)\n") is False
    assert prop_sat("exists x : bv[5]\n(5 * x) != ((x << 2) + x)\n") is False


def test_mul_is_commutative() -> None:
    assert prop_sat("exists x : bv[4]\nexists y : bv[4]\nx * y != y * x\n") is False


def test_mul_nontrivial_sanity() -> None:
    # 3*x == x only at x=0 ⇒ a counter-witness exists.
    assert prop_sat("exists x : bv[3]\n(3 * x) != x\n") is True


def test_ackermann_added_for_multiple_calls() -> None:
    # Structural: two call sites of f → Ackermann adds extra clauses beyond the
    # single-call case. (Semantic brute force doesn't scale here; CONTRADICTORY
    # already exercises same-arg congruence semantically.)
    one_call = compile_text("fun f: bv[1]->bv[1]\nforall a: bv[1]\nf(a)==a\n")
    two_calls = compile_text(
        "fun f: bv[1]->bv[1]\nforall a: bv[1]\nforall b: bv[1]\nf(a)==a\nf(b)==b\n"
    )
    assert len(two_calls.clauses) > 2 * len(one_call.clauses)
