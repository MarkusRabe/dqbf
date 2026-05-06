# random_qbf — Chen–Interian random QBF (2QBF, 3QBF)

**Problem.** Random k-CNF under a fixed quantifier prefix, with
clause/variable ratios tuned to the satisfiability phase transition so
the SAT/UNSAT split is roughly even.

**Encoding.** QDIMACS (linear `a`/`e` prefix only) — the **degenerate
DQBF case** with totally-ordered dependencies. Subfamilies:
- `v1/2qbf/` — `∀⁴∃⁸` blocks, 3-CNF, one universal lit per clause.
- `v2/2qbf/` — same shape, larger sizes.
- `v3/3qbf/` — `∃∀∃` three-block, the harder shape for clausal QBF
  solvers (∃-prefix prevents pure ∀-reduction at the leaves).

**What SAT/UNSAT mean.** SAT iff the inner-∃ player has a winning
strategy against every ∀ choice. `expected` is set by a `cadet` probe
in `label.py` (cross-checked, not constructed).

**Compare against.** This is the family where DQBF solvers can be
compared apples-to-apples with **QBF solvers**: cadet, caqe, rareqs,
depqbf consume the same `.qdimacs` directly. The runner registers them
under `domain="qbf"`.

**Literature.** Chen–Interian, *A Model for Generating Random
Quantified Boolean Formulas* (IJCAI'05); Creignou et al. on the QBF
phase transition; Lonsing–Biere, *DepQBF* (JSAT'10).
