# IC3 / PDR

## Citations

- **Bradley, A. R.** *SAT-Based Model Checking without Unrolling.*
  VMCAI 2011, LNCS 6538, pp. 70–87.
  [doi:10.1007/978-3-642-18275-4_7](https://link.springer.com/chapter/10.1007/978-3-642-18275-4_7) ·
  [PDF](https://theory.stanford.edu/~arbrad/papers/IC3.pdf)
- **Eén, N., Mishchenko, A., Brayton, R.** *Efficient Implementation of
  Property Directed Reachability.* FMCAD 2011, pp. 125–134.
  [PDF](https://people.eecs.berkeley.edu/~alanmi/publications/2011/fmcad11_pdr.pdf)
- **Bradley, A. R.** *Understanding IC3.* SAT 2012 (tutorial).
  [doi:10.1007/978-3-642-31612-8_1](https://link.springer.com/chapter/10.1007/978-3-642-31612-8_1)

## Problem

Given a finite-state transition system `(I, T)` over state variables
`x` (and primed copy `x'`) and a safety property `P(x)`, decide whether
every reachable state satisfies `P` — and if so, produce an *inductive
invariant* `Inv` with `I ⇒ Inv`, `Inv ∧ T ⇒ Inv'`, `Inv ⇒ P`; if not,
produce a counterexample trace.

Bounded model checking (BMC) unrolls `T` `k` times and SAT-checks
`I(x_0) ∧ ⋀ T(x_i,x_{i+1}) ∧ ¬P(x_k)`. It finds bugs but proves safety
only up to `k`; the unrolled formula grows linearly in `k` and the
solver sees no structure across depths.

## Core idea: incremental inductive strengthening

IC3 never unrolls. It maintains a finite sequence of **frames**
`F_0, F_1, …, F_k`, each a CNF over `x`, satisfying for all `i`:

1. `F_0 = I`
2. `F_i ⇒ F_{i+1}`  (syntactically: `clauses(F_{i+1}) ⊆ clauses(F_i)`)
3. `F_i ⇒ P`
4. `F_i ∧ T ⇒ F_{i+1}'`

So `F_i` over-approximates the states reachable in `≤ i` steps. The
algorithm grows `k` and tightens the frames until either some
`F_i = F_{i+1}` (then `F_i` is the inductive invariant) or a
counterexample trace is extracted.

## Relative induction and CTIs

A clause `c` is **inductive relative to `F_i`** if `I ⇒ c` and
`F_i ∧ c ∧ T ⇒ c'`. This is strictly weaker than ordinary
inductiveness (which would require `c ∧ T ⇒ c'`), and that weakening is
the whole point: we get to assume the over-approximation `F_i` already
established by earlier work.

When the outer loop tries to extend to a new frame `F_{k+1}`, it
SAT-checks `F_k ∧ T ∧ ¬P'`. A satisfying state `s ⊨ F_k` that can step
to `¬P` is a **counterexample to induction (CTI)**. IC3 *blocks* `s` by
searching for a clause `c` with `s ⊭ c` that is inductive relative to
`F_{k-1}`; `c` is then added to all frames `F_1..F_k`. If no such `c`
exists, `s` has a predecessor `s'` in `F_{k-1}` — recurse, blocking
`s'` at level `k-1`. If the recursion reaches level 0 with a state in
`I`, the chain of states is a real counterexample.

## Generalization

Blocking the single cube `¬s` would be sound but uselessly specific.
IC3 **generalizes** by dropping literals from `¬s` while the
relative-inductiveness query still succeeds; the surviving subclause
excludes a region of states, not just one. PDR adds **ternary
simulation**: simulate `T` from `s` with don't-cares to find which
state bits actually matter for reaching the bad successor, giving a
small starting cube before the SAT-based dropping.

## What PDR added

Eén–Mishchenko–Brayton recast the algorithm, named it PDR, and made it
practical: a priority queue of proof obligations (process the
lowest-level CTI first), delta-encoding of frames (store only the
clauses *new* at each level), aggressive subsumption, and clause
*pushing* (after each major iteration, try to lift every clause in
`F_i` to `F_{i+1}`). Their implementation in ABC won the Hardware
Model Checking Competition repeatedly; PDR-style engines have dominated
HWMCC since.

## Why it works

Every SAT call is over **one** copy of `T`, not `k` copies, so query
size stays bounded. Learned lemmas (clauses) persist across frames and
are reused, so the solver's work compounds. And the frame structure
gives a built-in termination check (fixpoint) that BMC lacks.

## Relation to this repository

`tools/bmc2dqbf/` and `tools/pec2dqbf/` are unrolling-based: they emit
a single (DQ)DIMACS instance per bound `k`. That's the right baseline,
but it inherits BMC's limits.

The natural lift is an IC3-style loop where the *frames* are DQBF
formulas and the *lemmas* are clauses learned by a fork-resolution
prover. Relative inductiveness `F_i ∧ c ∧ T ⇒ c'` is a one-step DQBF
validity query (universals over inputs, existentials over the
black-box outputs with their dependency restrictions) — exactly what
`provers/forkres/` decides. Generalization of CTIs corresponds to
strengthening a learned clause via ∀-reduction and FEx. The open
question is whether the FEx-introduced arbiter variables can be reused
across frames the way PDR reuses clauses, or whether each frame needs
its own fresh existentials.

Luka & Vizel's PdrER (see `arxiv_2505_18998.md`) shows that *extension
variables* — the propositional analogue of FEx's arbiters — pay off
inside a PDR loop. That is encouraging precedent.
