from core.compose import conjoin, shift
from core.formula import make_formula
from core.semantics import is_true


def f_sat():
    # ∀x1. ∃y2(x1). y2 ↔ x1  — SAT (y2 = x1)
    return make_formula(
        universals=[1],
        dependencies={2: [1]},
        clauses=[[-1, 2], [1, -2]],
    )


def f_unsat():
    # ∀x1 x2. ∃y3(x1). y3 ↔ x2  — UNSAT (y3 cannot see x2)
    return make_formula(
        universals=[1, 2],
        dependencies={3: [1]},
        clauses=[[-2, 3], [2, -3]],
    )


def test_shift_zero_is_identity() -> None:
    f = f_sat()
    g = shift(f, 0)
    assert g.n_vars == f.n_vars
    assert g.clauses == f.clauses


def test_shift_offsets_everything() -> None:
    f = f_sat()
    g = shift(f, 10)
    assert g.n_vars == 12
    assert g.universals == (11,)
    assert g.dependencies == {12: frozenset({11})}
    assert frozenset({-11, 12}) in g.clauses


def test_conjoin_disjoint_vars() -> None:
    a, b = f_sat(), f_sat()
    g = conjoin([a, b])
    assert g.n_vars == a.n_vars + b.n_vars
    assert len(g.universals) == 2
    assert len(g.dependencies) == 2
    assert len(g.clauses) == len(a.clauses) + len(b.clauses)
    # second component's vars shifted
    assert 3 in g.universals and 4 in g.dependencies


def test_conjoin_sat_iff_all_sat() -> None:
    assert is_true(conjoin([f_sat(), f_sat()])) is True
    assert is_true(conjoin([f_sat(), f_unsat()])) is False
    assert is_true(conjoin([f_unsat(), f_sat()])) is False
    assert is_true(conjoin([f_sat(), f_sat(), f_sat()])) is True


def test_conjoin_single() -> None:
    f = f_sat()
    g = conjoin([f])
    assert g.n_vars == f.n_vars
    assert set(g.clauses) == set(f.clauses)
