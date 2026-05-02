from core.certificate import skolem_from_json, skolem_to_json
from core.formula import make_formula
from core.semantics import find_skolem, is_true, verify_skolem


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


def test_verify_skolem_roundtrip() -> None:
    f = f_copy_sat()
    sk = find_skolem(f)
    assert sk is not None
    assert verify_skolem(f, sk)
    sk2 = skolem_from_json(skolem_to_json(f, sk))
    assert verify_skolem(f, sk2)


def test_verify_skolem_rejects_incomplete() -> None:
    f = make_formula(universals=[1], dependencies={2: [1]}, clauses=[[2]])
    incomplete: dict[int, dict[tuple[bool, ...], bool]] = {2: {(False,): True}}
    assert verify_skolem(f, incomplete) is False


def test_verify_skolem_rejects_wrong() -> None:
    f = f_copy_sat()
    bad: dict[int, dict[tuple[bool, ...], bool]] = {
        3: {(False,): True, (True,): False},
        4: {(False,): False, (True,): True},
    }
    assert verify_skolem(f, bad) is False
