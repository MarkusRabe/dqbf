from core.formula import make_formula
from provers.forkres.proof import Proof, replay


def test_replay_fex_sibling_pair() -> None:
    """Regression: emitting both FEx halves with the same fresh id must replay."""
    f = make_formula(universals=[1, 2], dependencies={3: [1], 4: [2]}, clauses=[[3, 4]])
    p = Proof()
    p.add(clause=(3, 4), rule="axiom")
    p.add(clause=(3, 5), rule="fex", premises=(0,), part=(3,), fresh=5)
    p.add(clause=(-5, 4), rule="fex", premises=(0,), part=(3,), fresh=5)
    p.add(clause=(3,), rule="ured", premises=(1,))
    p.add(clause=(4,), rule="ured", premises=(2,))
    # Not a refutation; just check the FEx steps don't cause replay to reject.
    # (replay returns False because ⊥ isn't derived; but it must not reject at step 2.)
    # To test acceptance of the steps themselves, append a fake ⊥ via res — instead,
    # check that replay reaches the end by adding a trivially-derivable ⊥ path:
    assert not replay(f, p)  # no ⊥, so False — but no early reject either:
    # Stronger check: if step 2 were rejected, derived would have len < 5.
    # Directly test: a full refutation that *requires* FEx.
    f2 = make_formula(
        universals=[1, 2],
        dependencies={3: [1], 4: [2]},
        clauses=[[3, 4], [-3], [-4]],
    )
    p2 = Proof()
    p2.add(clause=(3, 4), rule="axiom")
    p2.add(clause=(-3,), rule="axiom")
    p2.add(clause=(-4,), rule="axiom")
    p2.add(clause=(3, 5), rule="fex", premises=(0,), part=(3,), fresh=5)
    p2.add(clause=(-5, 4), rule="fex", premises=(0,), part=(3,), fresh=5)
    p2.add(clause=(5,), rule="res", premises=(3, 1), pivot=3)
    p2.add(clause=(-5,), rule="res", premises=(4, 2), pivot=4)
    p2.add(clause=(), rule="res", premises=(5, 6), pivot=5)
    assert replay(f2, p2)


def test_replay_rejects_wrong_fex() -> None:
    f = make_formula(universals=[1, 2], dependencies={3: [1], 4: [2]}, clauses=[[3, 4]])
    p = Proof()
    p.add(clause=(3, 4), rule="axiom")
    p.add(clause=(3, 99), rule="fex", premises=(0,), part=(3,), fresh=5)  # wrong fresh in clause
    assert not replay(f, p)
