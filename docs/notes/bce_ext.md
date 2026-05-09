# Can extension variables strengthen BCE?

Exploratory note. Propositional only — no quantifiers, no solvers.
Companion code: [`scripts/bce_ext_explore.py`](../../scripts/bce_ext_explore.py).

## The question

Blocked Clause Elimination (BCE) removes a clause `C` if some `l ∈ C`
has a tautological resolvent with *every* `D ∋ ¬l`. It iterates to a
unique fixpoint (BCE is confluent — Järvisalo, Biere, Heule, TACAS'10).
Extended Resolution introduces fresh variables `z` with definitional
clauses `Def(z) = Tseitin(z ↔ φ)`. **Can adding `Def(z)` before BCE
make BCE eliminate more?**

## Negative result: pure addition never helps

**Theorem.** For any CNF `F`, fresh variable `z ∉ vars(F)`, and any
2-input gate `φ` over `vars(F)`:

```
BCE(F ∪ Def(z)) = BCE(F).
```

**Proof.** Each clause in `Def(z)` is blocked on its `z`-literal in
`F ∪ Def(z)`: the only `¬z`-clauses are the other `Def(z)` clauses,
and Tseitin encodings of `z ↔ φ` self-resolve to tautologies (the
positive and negative phases of `z` cover complementary cubes of `φ`).
No clause of `F` mentions `z`. So `Def(z)` is a *blocked set* in
`F ∪ Def(z)`. Removing a clause never *un*-blocks another (resolvent
checks are universally quantified over the remaining clauses, so a
smaller formula has at most the same witnesses); by confluence we may
remove `Def(z)` first, leaving `F`, and then BCE proceeds exactly as
on `F` alone. ∎

Empirical check (`scripts/bce_ext_explore.py` §1): 9 873 random
(CNF, gate) pairs, 0 counterexamples.

The *mechanism* of the theorem is the right thing to internalize:
to make `C` blocked on `l`, **every** `D ∋ ¬l` must be tautological
when resolved. Adding clauses can only add `D`'s, never remove them.
So pure addition can only *un*-block, never block.

## What the directive's intuition was really after

The hypothesis "extension variables introduce structure that helps
elimination" is true, but the helpful operation is not *addition* —
it is **rewriting**. Two flavours:

1. **Bounded Variable Addition (BVA)** — Manthey, Heule, Biere
   (HVC'12). Introduce `z` and *replace* a `p×q` grid
   `{(lᵢ ∨ mⱼ)}` with `{(z ∨ mⱼ)} ∪ {(¬z ∨ lᵢ)}`. From `p·q` clauses
   to `p+q`. Equisatisfiable: `F ≡ (⋀lᵢ)∨(⋀mⱼ) ≡ ∃z.F'`. The savings
   come from the *factoring*, not from BCE seeing new blocked clauses.
   In our 2×3 example (`scripts` §3): BVA shrinks 8→7 and BCE removes
   nothing extra on either form.

2. **DRAT/RAT-clause addition with new variables** — Heule, Biere,
   "What a Difference a Variable Makes" (TACAS'18). Introducing
   variables and adding *RAT* clauses (a strict superclass of blocked
   clauses) is exactly Extended Resolution; it gives short proofs of
   PHP. But the RAT-addition step is a proof-system rule, not a
   preprocessing pass, and the search for the right `z` and the right
   RAT clauses is the whole hardness of ER.

Neither one is "BCE applied to a CNF with some extra extension
variables." Both are "extension as part of a reencoding," followed by
*any* downstream technique (which may or may not include BCE).

## Where extension genuinely creates new blocked literals

The operation that *can* make `C` newly-blocked is **removing or
rewriting the offending `D ∋ ¬l`**, which is what BVE (eliminate the
witness variable), BVA (factor `D` into `z`-clauses that resolve
tautologically), and resolution (replace `D` with a resolvent that
shares a complement with `C`) do.

```
F:       C = (a, x)   D = (¬x, b)         — C ⊗ₓ D = (a, b), not taut.
After resolving D with (¬b, ¬a) on b:
F':      C = (a, x)   D' = (¬x, ¬a)       — C ⊗ₓ D' = (a, ¬a), taut!
```

That `(¬b, ¬a)` could have come from a `z`-extension's Tseitin clauses
*resolved away*. So extension can be one step in a derivation that
ends up unblocking — but the derivation is doing the work, not BCE.

## The DQBF lift — where extension *directly* helps blockedness

Propositional BCE has no notion of variable scope. **DQBF-BCE** (see
`provers/frust/BCE.md`) requires the witness literal `p ∈ C\{l}` to
satisfy `dep(p) ⊆ dep(l)`. A clause whose only tautology witnesses
have *too-large* dep sets is never blockable by an original variable.

**FEx introduces a fresh existential whose dep set is the
intersection of two parents.** That dep set is strictly smaller than
either parent's, so a fork variable can witness blockedness where no
original variable could. This is *exactly* the propositional theorem
inverted: in the propositional case `dep(·) = U` for all variables,
so the dep check trivializes and extension adds nothing. The
quantified case is where extension's added structure is load-bearing
for elimination.

## Literature pointers

- Järvisalo, Biere, Heule, *Blocked Clause Elimination* (TACAS'10) —
  BCE definition, confluence, equivalence to Plaisted-Greenbaum.
- Kullmann, *On a generalization of extended resolution* (DAM 1999) —
  blocked clauses originate here, in the context of ER strength.
- Manthey, Heule, Biere, *Automated Reencoding of Boolean Formulas*
  (HVC'12) — BVA, the practical "extension that shrinks."
- Heule, Biere, *What a Difference a Variable Makes* (TACAS'18) —
  DRAT + new variables = ER; PHP becomes polynomial.
- Heule, Kiesl, Biere, *Strong Extension-Free Proof Systems*
  (J. Autom. Reasoning 2020) — the redundancy hierarchy
  BC ⊂ RAT ⊂ SPR ⊂ PR, and which need extension for short proofs.

## What it would take to make this a useful preprocessing step

For propositional CNF: don't bother — BVA already exists and is the
practical embodiment of "introduce `z` to shrink." Pairing BVA with
BCE in a preprocessing pipeline is sensible (and SAT solvers do this).
There is no separate "extension-augmented BCE" to invent.

For DQBF: the FEx-augmented BCE *is* novel and worth pursuing. The
preprocessing step would be:

1. Run DQBF-BCE to fixpoint.
2. For each surviving clause `C`, find the literal `l` whose
   blockedness is witnessed by the largest set of resolvent partners
   modulo dep — i.e., where the *only* obstruction is the dep check.
3. Introduce a fork variable `w` with `dep(w) = ⋂` of the deps of the
   would-be witnesses, and the appropriate `w`-clauses.
4. Re-run DQBF-BCE.

The cost: introducing `w` adds clauses, and the cert-reconstruction
for the eliminated clauses must thread through `w` (same machinery as
the FEx cert). The benefit: clauses with mixed-dep witnesses become
eliminable. Whether this fires often enough in practice to pay for
the extra variable is an empirical question for the solver loop.
