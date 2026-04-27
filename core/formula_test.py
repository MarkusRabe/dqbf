import pytest

from core.formula import Formula, make_formula


def test_make_formula_infers_nvars() -> None:
    f = make_formula(universals=[1, 2], dependencies={3: [1], 4: [2]}, clauses=[[3, 4], [-3, -4]])
    assert f.n_vars == 4
    assert f.existentials == (3, 4)
    assert f.dep(3) == {1}
    assert f.dep(1) == {1}
    assert f.clause_dep(frozenset({3, 4})) == {1, 2}


def test_validation_rejects_bad_dep() -> None:
    with pytest.raises(ValueError, match="non-universals"):
        make_formula(universals=[1], dependencies={2: [3]}, clauses=[])


def test_validation_rejects_dual_role() -> None:
    with pytest.raises(ValueError, match="both universal and existential"):
        Formula(n_vars=2, universals=(1,), dependencies={1: frozenset()}, clauses=())


def test_add_existential() -> None:
    f = make_formula(universals=[1, 2], dependencies={3: [1]}, clauses=[[3]])
    g = f.add_existential(4, frozenset({2}))
    assert g.n_vars == 4
    assert g.dependencies[4] == {2}
    assert f.n_vars == 3
