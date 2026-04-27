from core.formula import make_formula
from provers.forkres.rules import (
    find_information_fork,
    fork_extend,
    is_tautology,
    resolve,
    strong_fork_extend,
    universal_reduce,
)

F = make_formula(
    universals=[1, 2],
    dependencies={3: [1], 4: [2]},
    clauses=[],
)


def test_resolve_basic() -> None:
    r = resolve(frozenset({3, 4}), frozenset({-3, -4}), 3)
    assert r == frozenset({4, -4}) or r is None
    r2 = resolve(frozenset({3, 1}), frozenset({-3, 2}), 3)
    assert r2 == frozenset({1, 2})


def test_resolve_tautology_filtered() -> None:
    assert is_tautology(frozenset({4, -4}))
    r = resolve(frozenset({3, 4}), frozenset({-3, -4}), 3)
    assert r is None


def test_universal_reduce() -> None:
    # clause {1, 3}: var 1 universal, dep(3)={1} so 1 ∈ ex_deps → cannot drop
    assert universal_reduce(F, frozenset({1, 3})) == frozenset({1, 3})
    # clause {2, 3}: var 2 universal, dep(3)={1}, 2∉{1} → drop 2
    assert universal_reduce(F, frozenset({2, 3})) == frozenset({3})
    # clause {1, 2}: both universal, no existentials → drop both
    assert universal_reduce(F, frozenset({1, 2})) == frozenset()


def test_fork_extend() -> None:
    c = frozenset({3, 4})
    fr = fork_extend(F, c, frozenset({3}))
    assert fr.fresh == 5
    assert fr.formula.dependencies[5] == frozenset()  # dep{3}∩dep{4} = {1}∩{2} = ∅
    assert fr.left == frozenset({3, 5})
    assert fr.right == frozenset({4, -5})


def test_strong_fork_extend_drops_c3_universals() -> None:
    g = make_formula(universals=[1, 2, 3], dependencies={4: [1, 2], 5: [2, 3]}, clauses=[])
    c = frozenset({4, 5})
    fr = strong_fork_extend(g, c, frozenset({4}), c3=frozenset({2}))
    # dep{4}∩dep{5} = {2}; minus var(c3)={2} → ∅
    assert fr.formula.dependencies[fr.fresh] == frozenset()
    assert 2 in fr.left and 2 in fr.right


def test_find_information_fork() -> None:
    assert find_information_fork(F, frozenset({3, 4})) in {(3, 4), (4, 3)}
    assert find_information_fork(F, frozenset({3, 1})) is None
