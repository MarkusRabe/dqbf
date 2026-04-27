import pytest

from core.formula import make_formula
from core.semantics import is_true
from provers.forkres.search import Result, SearchConfig, solve

CFG = SearchConfig(max_clauses=2000, max_forks=16, timeout_s=1.0)


def test_unsat_wrong_dep() -> None:
    f = make_formula(
        universals=[1, 2],
        dependencies={3: [1]},
        clauses=[[-2, 3], [2, -3]],
    )
    res, _ = solve(f, CFG)
    assert res is Result.UNSAT


def test_sat_copy() -> None:
    f = make_formula(
        universals=[1, 2],
        dependencies={3: [1], 4: [2]},
        clauses=[[-1, 3], [1, -3], [-2, 4], [2, -4]],
    )
    res, _ = solve(f, CFG)
    assert res is Result.SAT


def test_unsat_with_fork() -> None:
    # ∀x1 x2. ∃y3(x1) ∃y4(x2). y3↔x2 ∧ y4↔x1  — both wrong-dep; needs FEx
    f = make_formula(
        universals=[1, 2],
        dependencies={3: [1], 4: [2]},
        clauses=[[-2, 3], [2, -3], [-1, 4], [1, -4]],
    )
    res, tr = solve(f, CFG)
    assert res is Result.UNSAT, tr.steps


@pytest.mark.parametrize("seed", range(6))
def test_soundness_against_semantics(seed: int) -> None:
    """For random tiny DQBF, prover never disagrees with the brute-force oracle."""
    import random

    rnd = random.Random(seed)
    universals = [1, 2]
    deps = {3: rnd.sample(universals, k=rnd.randint(0, 2)), 4: rnd.sample(universals, k=1)}
    lits = [1, -1, 2, -2, 3, -3, 4, -4]
    clauses = []
    for _ in range(rnd.randint(2, 5)):
        clauses.append(rnd.sample(lits, k=rnd.randint(1, 3)))
    f = make_formula(universals=universals, dependencies=deps, clauses=clauses)
    truth = is_true(f)
    res, _ = solve(f, CFG)
    if res is Result.SAT:
        assert truth is True
    elif res is Result.UNSAT:
        assert truth is False


def test_propositional_unsat() -> None:
    # No universals: pure SAT. {p}∧{¬p}
    f = make_formula(universals=[], dependencies={1: []}, clauses=[[1], [-1]])
    res, _ = solve(f, CFG)
    assert res is Result.UNSAT
