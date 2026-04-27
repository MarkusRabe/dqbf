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


def _dep_cycle_parity():
    """Journal §6 counterexample: y4⊕y5⊕y6 ↔ (x1∧x2∧x3) with cyclic deps."""
    parity = []
    for a in (4, -4):
        for b in (5, -5):
            for c in (6, -6):
                for d in (7, -7):
                    if sum(1 for x in (a, b, c, d) if x < 0) % 2 == 1:
                        parity.append([a, b, c, d])
    t_def = [[-7, 1], [-7, 2], [-7, 3], [7, -1, -2, -3]]
    return make_formula(
        universals=[1, 2, 3],
        dependencies={4: [1, 2], 5: [2, 3], 6: [1, 3], 7: [1, 2, 3]},
        clauses=parity + t_def,
    )


def test_sfex_fires_on_dep_cycle() -> None:
    """When FEx makes no progress (cyclic deps), SFEx must be applied."""
    f = _dep_cycle_parity()
    cfg = SearchConfig(max_clauses=5000, max_forks=64, timeout_s=1.0)
    out = solve(f, cfg)
    assert any("SFEx" in s for s in out.log), out.log
    if out.result is Result.UNSAT:
        assert out.proof is not None and replay(f, out.proof)
        assert any(s.rule == "sfex" for s in out.proof.steps)


def test_sfex_proof_step_replays() -> None:
    """A hand-built sfex step replays through the independent verifier."""
    from core.proof_trace import Proof

    f = make_formula(
        universals=[1, 2, 3],
        dependencies={4: [1, 2], 5: [2, 3], 6: [1, 3]},
        clauses=[[4, 5, 6], [-4], [-5], [-6]],
    )
    p = Proof()
    p.add(clause=(4, 5, 6), rule="axiom")
    p.add(clause=(-4,), rule="axiom")
    p.add(clause=(-5,), rule="axiom")
    p.add(clause=(-6,), rule="axiom")
    # SFEx on {4,5,6}, part={4}, c3={2}: dep4∩dep{5,6}={1,2}; drop 2 → dep(7)={1}
    p.add(clause=(2, 4, 7), rule="sfex", premises=(0,), part=(4,), c3=(2,), fresh=7)
    p.add(clause=(-7, 2, 5, 6), rule="sfex", premises=(0,), part=(4,), c3=(2,), fresh=7)
    # res + ∀-reduction (universal 2 ∉ dep(7)={1}, ∉ dep(6)={1,3})
    p.add(clause=(7,), rule="res", premises=(4, 1), pivot=4)
    p.add(clause=(-7, 6), rule="res", premises=(5, 2), pivot=5)
    p.add(clause=(-7,), rule="res", premises=(7, 3), pivot=6)
    p.add(clause=(), rule="res", premises=(6, 8), pivot=7)
    assert replay(f, p)


def test_propositional_unsat() -> None:
    f = make_formula(universals=[], dependencies={1: []}, clauses=[[1], [-1]])
    out = solve(f, CFG)
    assert out.result is Result.UNSAT
    assert out.proof is not None and replay(f, out.proof)
