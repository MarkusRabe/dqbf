# dep_cycle — the journal-§6 dependency-cycle counterexample

**Problem.** `∀x₁x₂x₃ . ∃ y₁(x₁,x₂), y₂(x₂,x₃), y₃(x₁,x₃) :
(y₁ ⊕ y₂ ⊕ y₃) == (x₁ ∧ x₂ ∧ x₃)`, lifted to `bv[N]`. **UNSAT for
every N** — the three pairwise-overlapping dependency sets form a
cycle that no Skolem assignment can satisfy.

**Why it matters.** This is the canonical instance that separates
fork-resolution from Q-resolution: plain FEx makes no progress because
no single fork shrinks the cycle; the proof requires **Strong Fork
Extension** (SFEx) or an equivalent expansion step. See journal §6 and
`tools/eqfob/examples/dep_cycle.eqfob`.

**Encoding.** EQFOB `fun` over three universals; the bit-blast keeps
the three incomparable dep-sets so the result is genuine DQBF (not
QBF). 4 instances at N ∈ {1,2,4,8}.

**Compare against.** dCAQE / HQS (expansion-based) solve N=1 by
brute-force expansion; iDQ/Pedant via instantiation. There is no
non-DQBF tool for this — it is the minimal genuinely-DQBF problem.

**Literature.** Rabe, *A Resolution-Style Proof System for DQBF*
(journal version, §6); Balabanov–Chiang–Jiang, *Henkin Quantifiers and
Boolean Formulae* (SAT'12) — the original DQBF complexity result.
