import pytest

from core.formula import make_formula
from core.semantics import is_true
from provers.forkres.proof import replay
from provers.forkres.search import Result, SearchConfig, solve
from tools.verify.sat import verify_skolem

CFG = SearchConfig(max_clauses=2000, max_forks=16, timeout_s=1.0)


def test_unsat_wrong_dep_with_proof() -> None:
    f = make_formula(
        universals=[1, 2],
        dependencies={3: [1]},
        clauses=[[-2, 3], [2, -3]],
    )
    out = solve(f, CFG)
    assert out.result is Result.UNSAT
    assert out.proof is not None and replay(f, out.proof)


def test_sat_copy_with_cert() -> None:
    f = make_formula(
        universals=[1, 2],
        dependencies={3: [1], 4: [2]},
        clauses=[[-1, 3], [1, -3], [-2, 4], [2, -4]],
    )
    out = solve(f, CFG)
    assert out.result is Result.SAT
    assert out.skolem is not None and verify_skolem(f, out.skolem)


def test_unsat_with_fork() -> None:
    f = make_formula(
        universals=[1, 2],
        dependencies={3: [1], 4: [2]},
        clauses=[[-2, 3], [2, -3], [-1, 4], [1, -4]],
    )
    out = solve(f, CFG)
    assert out.result is Result.UNSAT, out.log
    assert out.proof is not None and replay(f, out.proof)


@pytest.mark.parametrize("seed", range(8))
def test_soundness_against_semantics(seed: int) -> None:
    import random

    rnd = random.Random(seed)
    universals = [1, 2]
    deps = {3: rnd.sample(universals, k=rnd.randint(0, 2)), 4: rnd.sample(universals, k=1)}
    lits = [1, -1, 2, -2, 3, -3, 4, -4]
    clauses = [rnd.sample(lits, k=rnd.randint(1, 3)) for _ in range(rnd.randint(2, 5))]
    f = make_formula(universals=universals, dependencies=deps, clauses=clauses)
    truth = is_true(f)
    out = solve(f, CFG)
    if out.result is Result.SAT:
        assert truth is True
        assert out.skolem is not None and verify_skolem(f, out.skolem)
    elif out.result is Result.UNSAT:
        assert truth is False
        assert out.proof is not None and replay(f, out.proof)


def test_propositional_unsat() -> None:
    f = make_formula(universals=[], dependencies={1: []}, clauses=[[1], [-1]])
    out = solve(f, CFG)
    assert out.result is Result.UNSAT
    assert out.proof is not None and replay(f, out.proof)
