# Gitina et al. 2013 — PEC ↔ DQBF

## Citation

Karina Gitina, Sven Reimer, Matthias Sauer, Ralf Wimmer, Christoph
Scholl, Bernd Becker. **Equivalence Checking of Partial Designs Using
Dependency Quantified Boolean Formulae.** In *Proc. IEEE Int'l Conf.
on Computer Design (ICCD 2013)*, pp. 396–403.
DOI [10.1109/ICCD.2013.6657071](https://doi.org/10.1109/ICCD.2013.6657071) ·
[PDF](https://abs.informatik.uni-freiburg.de/papers/2013/GRS+_2013b.pdf)

## Problem: Partial Equivalence Checking (PEC)

A *specification* is a complete combinational circuit. An
*implementation* is a combinational circuit containing one or more
**black boxes** `BB₁,…,BBₘ` — modules whose internals are unknown
(unfinished, abstracted away, or removed for fault localisation). PEC
asks: **is there a realisation of every black box such that
implementation ≡ specification for all primary inputs?** If yes the
partial design is *realizable*; if not, the already-implemented portion
is provably wrong.

Prior approaches (Scholl & Becker 2001) decide PEC only approximately:
a SAT or QBF encoding that, on UNSAT, certifies unrealizability, but on
SAT proves nothing. With a single black box the strongest QBF
encoding is exact; with two or more black boxes whose input sets are
incomparable, no QBF prefix can express the correct dependency
constraints, so QBF over-approximates. The paper closes this gap by
giving an *exact* encoding into DQBF and a first algorithm to solve it.

## Main result

- **Lemma 1.** Any PEC instance translates to an equivalent DQBF in
  linear size (the encoding below).
- **Lemma 2.** Any DQBF translates to an equivalent PEC in linear size
  (one black box per existential, inputs = its dependency set, the
  matrix as a circuit required to output 1).
- **Theorem 1.** PEC and DQBF are polynomially equivalent.
- **Corollary 1.** PEC is **NEXPTIME-complete** (DQBF is, by
  Azhar–Peterson–Reif 2001).

## The encoding (PEC → DQBF, §III-A)

Let the implementation have primary inputs `x₁,…,xₙ`; black box `BBᵢ`
has input vector `⃗Iᵢ` and output vector `⃗Yᵢ`; the surrounding circuit
drives each `⃗Iᵢ` with `⃗Fᵢ(x₁..xₙ, ⃗Y₁..⃗Yᵢ₋₁)`; the miter output
(spec≡impl) is `R(x₁..xₙ, ⃗Y₁..⃗Yₘ)`. Black boxes are taken in
topological order, and a buffer is inserted wherever a black-box output
directly feeds another black box's input (so `⃗Yᵢ ∩ ⃗Iⱼ = ∅`; at most
linear blow-up).

**Prefix.**

```
∀x₁ … ∀xₙ  ∀⃗I₁ … ∀⃗Iₘ  ∃⃗Y₁(⃗I₁) … ∃⃗Yₘ(⃗Iₘ)  ∃⃗A(x₁..xₙ, ⃗I₁..⃗Iₘ)
```

- **Universals** = primary inputs *and* all black-box input wires.
- **Existentials** `⃗Yᵢ` = black-box output bits, with dependency set
  exactly `⃗Iᵢ` — the box can look only at its own pins.
- **Tseitin auxiliaries** `⃗A` (one per internal gate of the
  CNF-converted matrix) are existential with the *full* universal set as
  dependencies; they are bookkeeping, not synthesis targets.

**Matrix (Eq. 1, before Tseitin).**

```
(⃗I₁ ≢ ⃗F₁(x))  ∨ … ∨  (⃗Iₘ ≢ ⃗Fₘ(x, ⃗Y₁..⃗Yₘ₋₁))  ∨  R(x, ⃗Y₁..⃗Yₘ)
```

i.e. for every assignment to the universals: *either* some black-box
input vector is inconsistent with what the surrounding logic actually
drives onto it (in which case the assignment is irrelevant), *or* the
miter output holds. After Tseitin transformation the matrix is a CNF
linear in circuit size.

The DQBF is satisfied iff Skolem functions for every `⃗Yᵢ` exist making
the matrix a tautology — exactly the PEC realizability condition.

## Why DQBF and not QBF / SAT (§III-B)

A **QBF approximation** of the DQBF is any linearisation of the prefix
in which each `yᵢ` still appears to the right of every variable in its
dependency set (Def. 3). Lemma 3 shows `⊨ ψ_DQBF ⇒ ⊨ ψ_QBF`, so QBF
UNSAT proves DQBF UNSAT, but QBF SAT proves nothing. With a single
black box the unique strongest QBF approximation coincides with the
DQBF (Remark 1); with ≥2 boxes whose input sets are incomparable, every
linear prefix gives at least one `yᵢ` extra dependencies it does not
have in the circuit, allowing spurious Skolem functions. The running
example (`x₁ ⊕ x₂` spec, two one-input black boxes; Examples 1–4) is
DQBF-UNSAT, yet *both* strongest QBF approximations are SAT.

## Algorithm (§IV)

`henaig`: quantifier elimination on FRAIGs. **Theorem 2** eliminates a
universal `xᵢ` by conjoining the two cofactors `φ[0/xᵢ] ∧ φ[1/xᵢ]`,
duplicating every existential that depends on `xᵢ` in the second
cofactor. **Lemma 5** eliminates an existential whose dependency set is
*all* remaining universals by the standard `φ[0/y] ∨ φ[1/y]`.
**Algorithm 1** alternates: first drop existentials with full
dependencies (notably the Tseitin variables), then pick the universal
with the fewest dependent existentials, eliminate, repeat; finally hand
the universal-free residue to a SAT solver.

## Experiments (§V)

- **XOR templates** (Table I): for 2 black boxes, all 65 536 four-input
  functions as the surrounding circuit; for 3 and 4 black boxes,
  50 000 random instances each. Of the DQBF-UNSAT instances: with
  2 BBs only 50.6 % have *every* strongest-QBF approximation also
  UNSAT, 13.8 % have *every* QBF approximation wrong (SAT); with 4 BBs
  those numbers are <0.1 % and 43.4 %. Each instance solved in well
  under a second.
- **Carry-ripple adder** (Table II, benchmarks from [1]): 240 instances
  with 1–6 black boxes. With 6 black boxes only 31 of 2 160
  strongest-QBF approximations (1.4 %) give the correct UNSAT answer.
  Each instance ≤3 s.
- The prototype handles "a few hundred gates"; scalability is left as
  future work.

## Relation to this repository

- `tools/bmc2dqbf/` implements this encoding — the combinational case
  is exactly §III-A (PEC at unrolling depth `k = 0`); the sequential
  extension reuses the same black-box dependency set across time frames.
- `benchmarks/test/dqbf_qbflib/scholl/` are the Freiburg PEC instances
  descended from this and the follow-up work.
- `OVERVIEW.md` cites Theorem 1 / Corollary 1 for "PEC and DQBF are
  polynomially equivalent, both NEXPTIME-complete".
