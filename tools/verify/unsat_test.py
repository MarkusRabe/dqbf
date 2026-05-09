"""Tests for the self-contained UNSAT proof checker.

Hand-built traces only — no prover, no `core/` imports.

The FEx/SFEx tests in this file are the regression coverage for commit
`f672573`, which surfaced (and inverted) a long-standing crash in the
proof checker's FEx path: `unsat.py` calls a method on whatever
Formula type the caller supplied, but the two Formula implementations
(`tools.verify.formats.Formula` and `core.formula.Formula`) *did not
share a method name* until the follow-up rename in `formats.py`.
Either way the verifier crashed on FEx instead of returning a verdict,
which means every FEx/SFEx side-condition was effectively unchecked.
These tests pin every side-condition individually.
"""

from __future__ import annotations

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


# ---------------------------------------------------------------------------
# Valid proofs (positive coverage)
# ---------------------------------------------------------------------------


def test_simple_res_refutation() -> None:
    f = _f([], {1: []}, [[1], [-1]])
    p = _proof(
        {"clause": (1,), "rule": "axiom"},
        {"clause": (-1,), "rule": "axiom"},
        {"clause": (), "rule": "res", "premises": (0, 1), "pivot": 1},
    )
    assert verify_proof(f, p)


def _fex_refutation_formula_and_proof():
    """∀1 ∀2 ∃3(1) ∃4(2): {3,4} {¬3} {¬4}.  FEx splits {3,4} into
    {3,5} and {¬5,4} with fresh var 5, dep(5) = dep({3}) ∩ dep({4}) =
    {1} ∩ {2} = ∅."""
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
    return f, p


def test_fex_sibling_pair_replays() -> None:
    f, p = _fex_refutation_formula_and_proof()
    assert verify_proof(f, p)


def test_f672573_regression_fex_returns_not_raises() -> None:
    """Regression for `f672573`. The proof checker must *return* a
    verdict on FEx steps, not raise. Before that commit the call site
    was `g.with_existential` (the name `formats.Formula` had);
    `f672573` changed it to `g.add_existential` (the name
    `core.formula.Formula` had), which made the path crash for the
    `formats.Formula` callers — i.e. `cli.py` and this test file. The
    follow-up renames `formats.Formula.with_existential` →
    `add_existential` so both Formula types share the name. A crash is
    worse than INVALID for a verifier: harnesses tend to treat a
    crashed checker as "unknown" rather than "rejected"."""
    f, p = _fex_refutation_formula_and_proof()
    # If the method names ever drift apart again, this raises rather
    # than returning False — and pytest reports the AttributeError
    # plainly. Don't wrap in pytest.raises; the failure must be loud.
    result = verify_proof(f, p)
    assert isinstance(result, bool)
    assert result is True


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


def test_fused_res_then_ured() -> None:
    """The .frp emitter fuses res+∀Red into one `res` step
    (Q-resolution convention). The verifier accepts a `res` step whose
    claimed clause is a sound ∀-reduction of the resolvent. Pin this
    convention; the journal phrases the rules separately."""
    # ∀1 ∃2(): {1,2} {¬2}.  resolve on 2 → {1}.  dep(2)=∅ so ∀-red
    # drops 1 → {}.
    f = _f([1], {2: []}, [[1, 2], [-2]])
    p = _proof(
        {"clause": (1, 2), "rule": "axiom"},
        {"clause": (-2,), "rule": "axiom"},
        # Fused: claim {} directly, not {1}.
        {"clause": (), "rule": "res", "premises": (0, 1), "pivot": 2},
    )
    assert verify_proof(f, p)


# ---------------------------------------------------------------------------
# Invalid proofs (rejection coverage)
# ---------------------------------------------------------------------------


def test_rejects_non_axiom_clause() -> None:
    f = _f([], {1: []}, [[1]])
    assert not verify_proof(f, _proof({"clause": (-1,), "rule": "axiom"}))


def test_rejects_axiom_subset_of_input() -> None:
    """A strict *subset* of an input is not an axiom either."""
    f = _f([], {1: [], 2: []}, [[1, 2], [-1], [-2]])
    p = _proof({"clause": (1,), "rule": "axiom"})
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


def test_rejects_no_refutation() -> None:
    """A proof that's all-valid steps but never reaches ⊥."""
    f = _f([], {1: []}, [[1], [-1]])
    p = _proof({"clause": (1,), "rule": "axiom"}, {"clause": (-1,), "rule": "axiom"})
    assert not verify_proof(f, p)


def test_rejects_premise_out_of_range() -> None:
    f = _f([], {1: []}, [[1], [-1]])
    p = _proof(
        {"clause": (1,), "rule": "axiom"},
        {"clause": (), "rule": "res", "premises": (0, 99), "pivot": 1},
    )
    assert not verify_proof(f, p)


def test_rejects_forward_premise() -> None:
    """A premise index pointing at the current or a later step."""
    f = _f([], {1: []}, [[1], [-1]])
    p = _proof(
        {"clause": (1,), "rule": "axiom"},
        {"clause": (), "rule": "res", "premises": (0, 1), "pivot": 1},  # 1 = self
    )
    assert not verify_proof(f, p)


def test_rejects_res_pivot_not_in_premise() -> None:
    f = _f([], {1: [], 2: []}, [[1, 2], [-1, -2]])
    p = _proof(
        {"clause": (1, 2), "rule": "axiom"},
        {"clause": (-1, -2), "rule": "axiom"},
        # pivot 9 not in either premise
        {"clause": (), "rule": "res", "premises": (0, 1), "pivot": 9},
    )
    assert not verify_proof(f, p)


def test_rejects_res_same_polarity() -> None:
    f = _f([], {1: [], 2: []}, [[1, 2], [1, -2]])
    p = _proof(
        {"clause": (1, 2), "rule": "axiom"},
        {"clause": (1, -2), "rule": "axiom"},
        # pivot 1 has the same sign in both
        {"clause": (2, -2), "rule": "res", "premises": (0, 1), "pivot": 1},
    )
    assert not verify_proof(f, p)


def test_rejects_tautological_resolvent() -> None:
    """Q-res rejects a resolvent containing l and -l."""
    f = _f([], {1: [], 2: []}, [[1, 2], [-1, -2]])
    p = _proof(
        {"clause": (1, 2), "rule": "axiom"},
        {"clause": (-1, -2), "rule": "axiom"},
        # resolving on 1 → {2, -2}: tautology, must reject.
        {"clause": (2, -2), "rule": "res", "premises": (0, 1), "pivot": 1},
    )
    assert not verify_proof(f, p)


def test_rejects_ured_dropping_dependent_universal() -> None:
    """∀1 ∃2(1): cannot drop 1 from {1,2} because 1 ∈ dep(2)."""
    f = _f([1], {2: [1]}, [[1, 2]])
    p = _proof(
        {"clause": (1, 2), "rule": "axiom"},
        {"clause": (2,), "rule": "ured", "premises": (0,)},
    )
    assert not verify_proof(f, p)


def test_rejects_ured_adding_literals() -> None:
    """`ured` must produce a subset, never a superset."""
    f = _f([1], {2: []}, [[2]])
    p = _proof(
        {"clause": (2,), "rule": "axiom"},
        {"clause": (1, 2), "rule": "ured", "premises": (0,)},
    )
    assert not verify_proof(f, p)


def test_rejects_ured_dropping_existential() -> None:
    f = _f([1], {2: [], 3: []}, [[2, 3]])
    p = _proof(
        {"clause": (2, 3), "rule": "axiom"},
        {"clause": (2,), "rule": "ured", "premises": (0,)},
    )
    assert not verify_proof(f, p)


def test_rejects_ured_dropping_lit_whose_negation_present() -> None:
    """ured may not drop a universal literal `l` if `-l` is also in the
    clause (the clause is a tautology and dropping is unsound)."""
    f = _f([1], {2: []}, [[1, -1, 2]])
    p = _proof(
        {"clause": (1, -1, 2), "rule": "axiom"},
        {"clause": (-1, 2), "rule": "ured", "premises": (0,)},
    )
    assert not verify_proof(f, p)


# --- FEx / SFEx side conditions, one test per --------------------------------


def test_rejects_fex_part_not_subset() -> None:
    """`part` must be ⊆ the source clause."""
    f, _ = _fex_refutation_formula_and_proof()
    p = _proof(
        {"clause": (3, 4), "rule": "axiom"},
        # part {99} ⊄ {3,4}
        {"clause": (99, 5), "rule": "fex", "premises": (0,), "part": (99,), "fresh": 5},
    )
    assert not verify_proof(f, p)


def test_rejects_fex_claimed_clause_neither_half() -> None:
    f, _ = _fex_refutation_formula_and_proof()
    p = _proof(
        {"clause": (3, 4), "rule": "axiom"},
        # split is {3,5}|{4,-5}; claim something else.
        {"clause": (3, 4, 5), "rule": "fex", "premises": (0,), "part": (3,), "fresh": 5},
    )
    assert not verify_proof(f, p)


def test_rejects_fex_wrong_polarity() -> None:
    """Left half must carry +fresh; right half -fresh; not swapped."""
    f, _ = _fex_refutation_formula_and_proof()
    p = _proof(
        {"clause": (3, 4), "rule": "axiom"},
        # part is {3} so left should be {3, 5}; here we claim {3, -5}.
        {"clause": (3, -5), "rule": "fex", "premises": (0,), "part": (3,), "fresh": 5},
    )
    assert not verify_proof(f, p)


def test_rejects_fex_fresh_collides_with_universal() -> None:
    f, _ = _fex_refutation_formula_and_proof()
    p = _proof(
        {"clause": (3, 4), "rule": "axiom"},
        {"clause": (3, 1), "rule": "fex", "premises": (0,), "part": (3,), "fresh": 1},
    )
    assert not verify_proof(f, p)


def test_rejects_fex_fresh_collides_with_existential() -> None:
    f, _ = _fex_refutation_formula_and_proof()
    p = _proof(
        {"clause": (3, 4), "rule": "axiom"},
        {"clause": (3, 4), "rule": "fex", "premises": (0,), "part": (3,), "fresh": 4},
    )
    assert not verify_proof(f, p)


def test_rejects_fex_fresh_within_n_vars() -> None:
    """Even an *unused* var id ≤ n_vars must be rejected as not
    fresh — the prefix may have unmentioned vars in that range."""
    f = _f([1, 2], {3: [1], 4: [2]}, [[3, 4]])
    # n_vars is 4; fresh must be > 4.
    p = _proof(
        {"clause": (3, 4), "rule": "axiom"},
        {"clause": (3, 4), "rule": "fex", "premises": (0,), "part": (3,), "fresh": 4},
    )
    assert not verify_proof(f, p)


def test_rejects_fex_reused_fresh_with_different_part() -> None:
    """A fresh var introduced once may only be re-used by the sibling
    half of the *same* fork. Re-using with a different part must be
    rejected."""
    f = _f([1, 2], {3: [1], 4: [2]}, [[3, 4], [-3], [-4]])
    p = _proof(
        {"clause": (3, 4), "rule": "axiom"},
        {"clause": (3, 5), "rule": "fex", "premises": (0,), "part": (3,), "fresh": 5},
        # same fresh 5, but part is now {4} — different sig.
        {"clause": (4, 5), "rule": "fex", "premises": (0,), "part": (4,), "fresh": 5},
    )
    assert not verify_proof(f, p)


def test_rejects_fex_reused_fresh_with_different_premise() -> None:
    """Same part but different source clause."""
    f = _f([1, 2], {3: [1], 4: [2]}, [[3, 4], [3, -4], [-3], [-4]])
    p = _proof(
        {"clause": (3, 4), "rule": "axiom"},
        {"clause": (3, -4), "rule": "axiom"},
        {"clause": (3, 5), "rule": "fex", "premises": (0,), "part": (3,), "fresh": 5},
        # same fresh, same part, different premise.
        {"clause": (3, 5), "rule": "fex", "premises": (1,), "part": (3,), "fresh": 5},
    )
    assert not verify_proof(f, p)


def test_rejects_fex_reused_fresh_after_sfex() -> None:
    """A var introduced by a `fex` step may not be reused by a `sfex`
    step (different rule, even with the same other fields — the
    signature includes the rule)."""
    f = _f([1, 2], {3: [1], 4: [2]}, [[3, 4], [-3], [-4]])
    p = _proof(
        {"clause": (3, 4), "rule": "axiom"},
        {"clause": (3, 5), "rule": "fex", "premises": (0,), "part": (3,), "fresh": 5},
        {"clause": (3, 5), "rule": "sfex", "premises": (0,), "part": (3,), "c3": (), "fresh": 5},
    )
    assert not verify_proof(f, p)


def test_fex_dep_intersection_used_downstream() -> None:
    """The verifier records dep(fresh) = clause_dep(C₁) ∩ clause_dep(C₂),
    where clause_dep counts universal vars themselves AND deps of
    existentials. If it accepted a too-large dep (e.g., union), a
    downstream `ured` would fail. This proof is valid only if dep(5) = ∅
    — which happens when C₁'s and C₂'s clause-deps are *disjoint*."""
    # ∀1 ∀2 ∃3(1) ∃4(2). C={3,4}; part={3}: clause_dep({3})={1},
    # clause_dep({4})={2}, intersection=∅.
    f = _f([1, 2], {3: [1], 4: [2]}, [[1, 3, 4], [-3], [-4]])
    p = _proof(
        {"clause": (1, 3, 4), "rule": "axiom"},
        {"clause": (-3,), "rule": "axiom"},
        {"clause": (-4,), "rule": "axiom"},
        # FEx: part={3}; clause_dep({3})={1}; clause_dep({1,4})={1,2};
        # intersection={1}. So dep(5)={1}.
        {"clause": (3, 5), "rule": "fex", "premises": (0,), "part": (3,), "fresh": 5},
        {"clause": (-5, 1, 4), "rule": "fex", "premises": (0,), "part": (3,), "fresh": 5},
        {"clause": (5,), "rule": "res", "premises": (3, 1), "pivot": 3},
        {"clause": (-5, 1), "rule": "res", "premises": (4, 2), "pivot": 4},
        # 1 ∈ dep(5) so this ured MUST FAIL — the verifier records
        # dep(5)={1}. If it recorded ∅ (too small), this would
        # wrongly pass and the proof would (unsoundly) verify.
        {"clause": (-5,), "rule": "ured", "premises": (6,)},
        {"clause": (), "rule": "res", "premises": (5, 7), "pivot": 5},
    )
    assert not verify_proof(f, p)


def test_fex_dep_too_small_rejected_downstream() -> None:
    """The opposite direction: if the verifier recorded dep(fresh) too
    small, a downstream `ured` could drop a universal that fresh
    actually depends on. Build a case where the intersection is {1}
    (non-empty) and a `ured` dropping 1 from a clause containing fresh
    must be rejected."""
    f = _f([1, 2], {3: [1, 2], 4: [1]}, [[3, 4, 1], [-3], [-4]])
    p = _proof(
        {"clause": (3, 4, 1), "rule": "axiom"},
        {"clause": (-3,), "rule": "axiom"},
        # dep(5) = dep({3}) ∩ dep({4,1}) = {1,2} ∩ {1} = {1}.
        {"clause": (3, 5), "rule": "fex", "premises": (0,), "part": (3,), "fresh": 5},
        {"clause": (-5, 4, 1), "rule": "fex", "premises": (0,), "part": (3,), "fresh": 5},
        # 1 ∈ dep(5), so ured dropping 1 from {-5, 4, 1} is unsound.
        {"clause": (-5, 4), "rule": "ured", "premises": (3,)},
    )
    assert not verify_proof(f, p)


def test_rejects_fex_zero_premises() -> None:
    f, _ = _fex_refutation_formula_and_proof()
    p = _proof(
        {"clause": (3, 4), "rule": "axiom"},
        {"clause": (3, 5), "rule": "fex", "premises": (), "part": (3,), "fresh": 5},
    )
    assert not verify_proof(f, p)


def test_rejects_fex_two_premises() -> None:
    f, _ = _fex_refutation_formula_and_proof()
    p = _proof(
        {"clause": (3, 4), "rule": "axiom"},
        {"clause": (-3,), "rule": "axiom"},
        {"clause": (3, 5), "rule": "fex", "premises": (0, 1), "part": (3,), "fresh": 5},
    )
    assert not verify_proof(f, p)


def test_rejects_fex_missing_part() -> None:
    f, _ = _fex_refutation_formula_and_proof()
    p = _proof(
        {"clause": (3, 4), "rule": "axiom"},
        {"clause": (3, 5), "rule": "fex", "premises": (0,), "fresh": 5},
    )
    assert not verify_proof(f, p)


def test_rejects_fex_missing_fresh() -> None:
    f, _ = _fex_refutation_formula_and_proof()
    p = _proof(
        {"clause": (3, 4), "rule": "axiom"},
        {"clause": (3, 5), "rule": "fex", "premises": (0,), "part": (3,)},
    )
    assert not verify_proof(f, p)


def test_rejects_sfex_c3_existential() -> None:
    """SFEx's c3 must be all-universal."""
    f = _f([1, 2], {3: [1], 4: [2]}, [[3, 4], [-3], [-4]])
    p = _proof(
        {"clause": (3, 4), "rule": "axiom"},
        # c3 = {3}: 3 is existential.
        {"clause": (3, 5), "rule": "sfex", "premises": (0,), "part": (3,), "c3": (3,), "fresh": 5},
    )
    assert not verify_proof(f, p)


def test_rejects_sfex_c3_dropped_from_claimed_clause() -> None:
    """The c3 lits must actually appear in the claimed clause."""
    f = _f([1, 2, 3], {4: [1], 5: [2]}, [[4, 5], [-4], [-5]])
    p = _proof(
        {"clause": (4, 5), "rule": "axiom"},
        # left half should be {3, 4, 6}; we drop 3.
        {"clause": (4, 6), "rule": "sfex", "premises": (0,), "part": (4,), "c3": (3,), "fresh": 6},
    )
    assert not verify_proof(f, p)


def test_sfex_dep_subtraction_used_downstream() -> None:
    """SFEx's dep(fresh) subtracts var(c3). If it didn't, a downstream
    ured dropping var(c3) would fail. We build a proof that requires
    the subtraction.

    ∀1 ∀2 ∃3(1) ∃4(2): {3,4} {¬3} {¬4}.  SFEx c3={1}.
    dep(5) = (dep{3} ∩ dep{4}) ∖ {1} = ({1} ∩ {2}) ∖ {1} = ∅.
    """
    f = _f([1, 2], {3: [1], 4: [2]}, [[3, 4], [-3], [-4]])
    p = _proof(
        {"clause": (3, 4), "rule": "axiom"},
        {"clause": (-3,), "rule": "axiom"},
        {"clause": (-4,), "rule": "axiom"},
        {
            "clause": (1, 3, 5),
            "rule": "sfex",
            "premises": (0,),
            "part": (3,),
            "c3": (1,),
            "fresh": 5,
        },
        {
            "clause": (-5, 1, 4),
            "rule": "sfex",
            "premises": (0,),
            "part": (3,),
            "c3": (1,),
            "fresh": 5,
        },
        {"clause": (1, 5), "rule": "res", "premises": (3, 1), "pivot": 3},
        # 1 ∉ dep(5) (= ∅) so the ured may drop 1.
        {"clause": (5,), "rule": "ured", "premises": (5,)},
        {"clause": (-5, 1), "rule": "res", "premises": (4, 2), "pivot": 4},
        {"clause": (-5,), "rule": "ured", "premises": (7,)},
        {"clause": (), "rule": "res", "premises": (6, 8), "pivot": 5},
    )
    assert verify_proof(f, p)


def test_sfex_with_empty_c3_is_fex() -> None:
    """SFEx with c3=∅ degenerates to FEx; both should be accepted."""
    f, _ = _fex_refutation_formula_and_proof()
    p_sfex = _proof(
        {"clause": (3, 4), "rule": "axiom"},
        {"clause": (-3,), "rule": "axiom"},
        {"clause": (-4,), "rule": "axiom"},
        {"clause": (3, 5), "rule": "sfex", "premises": (0,), "part": (3,), "c3": (), "fresh": 5},
        {"clause": (-5, 4), "rule": "sfex", "premises": (0,), "part": (3,), "c3": (), "fresh": 5},
        {"clause": (5,), "rule": "res", "premises": (3, 1), "pivot": 3},
        {"clause": (-5,), "rule": "res", "premises": (4, 2), "pivot": 4},
        {"clause": (), "rule": "res", "premises": (5, 6), "pivot": 5},
    )
    assert verify_proof(f, p_sfex)


# ---------------------------------------------------------------------------
# Documented leniencies (Python accepts; Rust verifier rejects; both safe-
# direction). Pinned so a future tightening is a visible decision, not drift.
# ---------------------------------------------------------------------------


def test_lenient_axiom_with_spurious_premises() -> None:
    """Python accepts an `axiom` step carrying a `premises` field it
    ignores. Benign metadata leniency. See `docs/notes/verifier_risks.md`."""
    f = _f([], {1: []}, [[1], [-1]])
    p = _proof(
        {"clause": (1,), "rule": "axiom", "premises": (0,)},  # spurious
        {"clause": (-1,), "rule": "axiom"},
        {"clause": (), "rule": "res", "premises": (0, 1), "pivot": 1},
    )
    assert verify_proof(f, p)


def test_lenient_ured_noop() -> None:
    """Python accepts a `ured` step that drops nothing (dst == src).
    Sound (drops the empty set), but suspicious. Pinned so tightening
    is tracked."""
    f = _f([1], {2: []}, [[2], [-2]])
    p = _proof(
        {"clause": (2,), "rule": "axiom"},
        {"clause": (-2,), "rule": "axiom"},
        {"clause": (2,), "rule": "ured", "premises": (0,)},  # no-op
        {"clause": (), "rule": "res", "premises": (2, 1), "pivot": 2},
    )
    assert verify_proof(f, p)
