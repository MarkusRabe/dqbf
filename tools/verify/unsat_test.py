"""Tests for the self-contained UNSAT proof checker.

Hand-built traces only — no prover, no `core/` imports.
"""

from tools.verify.formats import Formula, Proof, Step
from tools.verify.unsat import verify_proof


def _f(universals, deps, clauses) -> Formula:
    return Formula(
        n_vars=max([*universals, *deps, *(abs(x) for c in clauses for x in c)], default=0),
        universals=tuple(universals),
        dependencies={y: frozenset(d) for y, d in deps.items()},
        clauses=tuple(frozenset(c) for c in clauses),
    )


def _proof(*steps) -> Proof:
    return Proof(steps=[Step(**s) for s in steps])


def test_simple_res_refutation() -> None:
    f = _f([], {1: []}, [[1], [-1]])
    p = _proof(
        {"clause": (1,), "rule": "axiom"},
        {"clause": (-1,), "rule": "axiom"},
        {"clause": (), "rule": "res", "premises": (0, 1), "pivot": 1},
    )
    assert verify_proof(f, p)


def test_fex_sibling_pair_replays() -> None:
    f = _f([1, 2], {3: [1], 4: [2]}, [[3, 4], [-3], [-4]])
    p = _proof(
        {"clause": (3, 4), "rule": "axiom"},
        {"clause": (-3,), "rule": "axiom"},
        {"clause": (-4,), "rule": "axiom"},
        {"clause": (3, 5), "rule": "fex", "premises": (0,), "part": (3,), "fresh": 5},
        {"clause": (-5, 4), "rule": "fex", "premises": (0,), "part": (3,), "fresh": 5},
        {"clause": (5,), "rule": "res", "premises": (3, 1), "pivot": 3},
        {"clause": (-5,), "rule": "res", "premises": (4, 2), "pivot": 4},
        {"clause": (), "rule": "res", "premises": (5, 6), "pivot": 5},
    )
    assert verify_proof(f, p)


def test_rejects_non_axiom_clause() -> None:
    f = _f([], {1: []}, [[1]])
    p = _proof({"clause": (-1,), "rule": "axiom"})
    assert not verify_proof(f, p)


def test_rejects_wrong_resolvent() -> None:
    f = _f([], {1: [], 2: []}, [[1, 2], [-1]])
    p = _proof(
        {"clause": (1, 2), "rule": "axiom"},
        {"clause": (-1,), "rule": "axiom"},
        {"clause": (1,), "rule": "res", "premises": (0, 1), "pivot": 1},
    )
    assert not verify_proof(f, p)


def test_rejects_unknown_rule() -> None:
    f = _f([], {1: []}, [[1]])
    assert not verify_proof(f, _proof({"clause": (1,), "rule": "bogus"}))


def test_sfex_refutation() -> None:
    """SFEx with c3={2}: dep(7) = (dep4 ∩ dep{5,6}) ∖ {2} = {1}."""
    f = _f(
        [1, 2, 3],
        {4: [1, 2], 5: [2, 3], 6: [1, 3]},
        [[4, 5, 6], [-4], [-5], [-6]],
    )
    p = _proof(
        {"clause": (4, 5, 6), "rule": "axiom"},
        {"clause": (-4,), "rule": "axiom"},
        {"clause": (-5,), "rule": "axiom"},
        {"clause": (-6,), "rule": "axiom"},
        {
            "clause": (2, 4, 7),
            "rule": "sfex",
            "premises": (0,),
            "part": (4,),
            "c3": (2,),
            "fresh": 7,
        },
        {
            "clause": (-7, 2, 5, 6),
            "rule": "sfex",
            "premises": (0,),
            "part": (4,),
            "c3": (2,),
            "fresh": 7,
        },
        {"clause": (7,), "rule": "res", "premises": (4, 1), "pivot": 4},
        {"clause": (-7, 6), "rule": "res", "premises": (5, 2), "pivot": 5},
        {"clause": (-7,), "rule": "res", "premises": (7, 3), "pivot": 6},
        {"clause": (), "rule": "res", "premises": (6, 8), "pivot": 7},
    )
    assert verify_proof(f, p)


def test_ured() -> None:
    f2 = _f([1, 2], {3: [1]}, [[2, 3], [-3]])
    p2 = _proof(
        {"clause": (2, 3), "rule": "axiom"},
        {"clause": (-3,), "rule": "axiom"},
        {"clause": (3,), "rule": "ured", "premises": (0,)},
        {"clause": (), "rule": "res", "premises": (2, 1), "pivot": 3},
    )
    assert verify_proof(f2, p2)
