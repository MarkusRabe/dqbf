"""Tiny worked examples mapping each of frust's no-cert UNSAT paths
to fork-resolution `.frp` proofs, checked by `tools/verify/unsat.py`.

Paths:
  1. CDCL row-UNSAT (expand / CegarOut::Unsat)
  2. SlotDpll exhausted
  3. arbsolve-UNSAT
"""
from __future__ import annotations

from core.formula import Formula
from core.proof_trace import Proof
from tools.verify.unsat import verify_proof


def build(us: list[int], deps: dict[int, set[int]], cls: list[list[int]]) -> Formula:
    return Formula(
        n_vars=max(max(us, default=0), max(deps, default=0)),
        universals=tuple(us),
        dependencies={e: frozenset(d) for e, d in deps.items()},
        clauses=tuple(frozenset(c) for c in cls),
    )


# ───────────────────────── Path 1: CDCL row-UNSAT ─────────────────────
# ∀u ∃y(u): (u∨y) ∧ (u∨¬y).  Row u=0 is propositionally UNSAT.
# CDCL: assume ¬u; (u∨y) propagates y; (u∨¬y) conflicts.
# 1-UIP resolves the two reason clauses on y → (u); ∀-reduce → ⊥.
# Universal assumptions never become pivots (they sit at level 0), so
# every CDCL pivot is existential ⇒ the chain is already Q-resolution.
f1 = build(us=[1], deps={2: {1}}, cls=[[1, 2], [1, -2]])
p1 = Proof()
i0 = p1.add(clause=(1, 2), rule="axiom")
i1 = p1.add(clause=(1, -2), rule="axiom")
p1.add(clause=(), rule="res", premises=(i0, i1), pivot=2)
print("path1 row-UNSAT:", "OK" if verify_proof(f1, p1) else "FAIL")


# ──────────────────── Path 1b: row-UNSAT with two universals ──────────
# ∀u₁u₂ ∃y(u₁,u₂): (u₁∨y) ∧ (u₂∨¬y).  Row (0,0) UNSAT.
# Resolve on y → (u₁∨u₂); ∀-reduce → ⊥ (no existentials remain).
f1b = build(us=[1, 2], deps={3: {1, 2}}, cls=[[1, 3], [2, -3]])
p1b = Proof()
i0 = p1b.add(clause=(1, 3), rule="axiom")
i1 = p1b.add(clause=(2, -3), rule="axiom")
p1b.add(clause=(), rule="res", premises=(i0, i1), pivot=3)
print("path1b row-UNSAT 2u:", "OK" if verify_proof(f1b, p1b) else "FAIL")


# ────────────── Path 4: arbsolve-UNSAT (constant existential) ─────────
# ∀u ∃y(∅): (u∨y) ∧ (¬u∨¬y).  y must equal ¬u but dep(y)=∅ ⇒ UNSAT.
# arbsolve: y=0 fails at u=0 (clause 1); y=1 fails at u=1 (clause 2).
# Q-res: resolving the two clauses on y is a tautology (u∨¬u). But
# u∉dep(y), so ∀-reduce *first*: (u∨y)→(y), (¬u∨¬y)→(¬y), then res→⊥.
# General form: each arbsolve conflict points at a clause-set that
# (after ∀-reducing universals outside dep(y)) resolves on y to ⊥.
f4 = build(us=[1], deps={2: set()}, cls=[[1, 2], [-1, -2]])
p4 = Proof()
i0 = p4.add(clause=(1, 2), rule="axiom")
i1 = p4.add(clause=(-1, -2), rule="axiom")
i2 = p4.add(clause=(2,), rule="ured", premises=(i0,))
i3 = p4.add(clause=(-2,), rule="ured", premises=(i1,))
p4.add(clause=(), rule="res", premises=(i2, i3), pivot=2)
print("path4 arb const:", "OK" if verify_proof(f4, p4) else "FAIL")


# ─────── Path 4b: arbsolve-UNSAT, 2 cells (the canonical fork) ────────
# ∀u₁u₂ ∃y(u₁) z(u₂): y↔u₂ ∧ z↔u₁ ∧ y↔z.  This is fork_unsat.
# y has 2 cells (u₁=0, u₁=1); z has 2 cells. arbsolve searches 4×4=16
# assignments, all fail. The fork-res proof is the textbook FEx
# derivation — exactly what frust's *saturate* path already emits.
# So the mapping for arbsolve's per-cell vars is: each cell of y at
# dep-row r corresponds to a FEx-introduced fork variable.
#
# Question: can the *arbsolve trace* be replayed as FEx + Q-res, or do
# we need saturate to re-derive it? Test: load fork_unsat, run saturate
# (which already certs it), and confirm the cert structure matches what
# arbsolve's conflict tree would produce.
print()
# fork_unsat as it stands: y(x₁) constrained by x₂, z(x₂) by x₁.
# Since x₂∉dep(y), ∀-reduce drops x₂ from the y-clauses → (y),(¬y)→⊥.
# No FEx needed! arbsolve "exhausts cells" but the proof is just ∀-red.
f5 = build(
    us=[1, 2],
    deps={3: {1}, 4: {2}},
    cls=[[-2, 3], [2, -3], [-1, 4], [1, -4]],
)
p5 = Proof()
i0 = p5.add(clause=(-2, 3), rule="axiom")
i1 = p5.add(clause=(2, -3), rule="axiom")
i2 = p5.add(clause=(3,), rule="ured", premises=(i0,))
i3 = p5.add(clause=(-3,), rule="ured", premises=(i1,))
p5.add(clause=(), rule="res", premises=(i2, i3), pivot=3)
print("path4b fork_unsat (no FEx):", "OK" if verify_proof(f5, p5) else "FAIL")


# ───── Path 4c: arbsolve-UNSAT where FEx is genuinely needed ──────────
# ∀u₁u₂ ∃y(u₁) z(u₂): (y∨z) ∧ (¬y∨¬z) ∧ (¬u₁∨u₂∨y) ∧ (u₁∨¬u₂∨¬y)
# Neither u₁ nor u₂ can be ∀-reduced from the first two clauses
# (u₁∈dep(y), u₂∈dep(z) — both deps cover the lit). Q-res alone:
# resolve (y∨z),(¬y∨¬z) on y → (z∨¬z) tautology. Stuck.
# This needs FEx: split (y∨z) into c1={y}, c2={z}; fresh w with
# dep = dep(y)∩dep(z) = ∅. Gives (y∨w) and (z∨¬w). Then ...
f6 = build(
    us=[1, 2],
    deps={3: {1}, 4: {2}},
    cls=[[3, 4], [-3, -4], [-1, 2, 3], [1, -2, -3]],
)
# First, is it actually UNSAT? Semantics check.
from core.semantics import is_true
print(f"path4c truth: {'SAT' if is_true(f6) else 'UNSAT'}")
# FEx attempt:
p6 = Proof()
i0 = p6.add(clause=(3, 4), rule="axiom")
i1 = p6.add(clause=(-3, -4), rule="axiom")
# FEx on clause 0: part={3}, fresh=5, dep(5)=dep({3})∩dep({4})={1}∩{2}=∅
p6.add(clause=(3, 5), rule="fex", premises=(i0,), part=(3,), fresh=5)  # i2
p6.add(clause=(4, -5), rule="fex", premises=(i0,), part=(3,), fresh=5)  # i3
# FEx on clause 1: part={-3}, fresh=6, dep=∅
p6.add(clause=(-3, 6), rule="fex", premises=(i1,), part=(-3,), fresh=6)  # i4
p6.add(clause=(-4, -6), rule="fex", premises=(i1,), part=(-3,), fresh=6)  # i5
# Now: (3,5) res (-3,6) on 3 → (5,6); ∀-red trivial. (4,-5) res (-4,-6) on 4 → (-5,-6).
i6 = p6.add(clause=(5, 6), rule="res", premises=(2, 4), pivot=3)
i7 = p6.add(clause=(-5, -6), rule="res", premises=(3, 5), pivot=4)
# (5,6) res (-5,-6) on 5 → (6,-6) tautology — Q-res rejects.
# Need clauses 3/4 from the matrix to break symmetry.
i8 = p6.add(clause=(-1, 2, 3), rule="axiom")
i9 = p6.add(clause=(1, -2, -3), rule="axiom")
# ∀-reduce: -1∈dep(3)? var 1∈{1}=dep(3) — can't drop. var 2∉dep(3) → drop 2.
i10 = p6.add(clause=(-1, 3), rule="ured", premises=(i8,))
i11 = p6.add(clause=(1, -3), rule="ured", premises=(i9,))
# (3,5) from FEx res (1,-3) → (1,5). dep(5)=∅ so ∀-red 1 → (5).
i12 = p6.add(clause=(5,), rule="res", premises=(2, i11), pivot=3)
# (-3,6) res (-1,3) → (-1,6). ∀-red 1 → (6).
i13 = p6.add(clause=(6,), rule="res", premises=(4, i10), pivot=3)
# (-5,-6) res (5) → (-6). res (6) → ⊥.
i14 = p6.add(clause=(-6,), rule="res", premises=(i7, i12), pivot=5)
p6.add(clause=(), rule="res", premises=(i14, i13), pivot=6)
print("path4c FEx proof:", "OK" if verify_proof(f6, p6) else "FAIL")
