from core.formula import make_formula
from core.semantics import find_skolem, is_true


def f_copy_sat():
    # ∀x1 x2. ∃y3(x1) ∃y4(x2). (y3↔x1) ∧ (y4↔x2)  — SAT via y3=x1, y4=x2
    return make_formula(
        universals=[1, 2],
        dependencies={3: [1], 4: [2]},
        clauses=[[-1, 3], [1, -3], [-2, 4], [2, -4]],
    )


def f_wrong_dep_unsat():
    # ∀x1 x2. ∃y3(x1). (y3↔x2)  — UNSAT (y3 cannot see x2)
    return make_formula(
        universals=[1, 2],
        dependencies={3: [1]},
        clauses=[[-2, 3], [2, -3]],
    )


def test_is_true_sat() -> None:
    assert is_true(f_copy_sat()) is True
    sk = find_skolem(f_copy_sat())
    assert sk is not None
    assert sk[3][(False,)] is False and sk[3][(True,)] is True


def test_is_true_unsat() -> None:
    assert is_true(f_wrong_dep_unsat()) is False
