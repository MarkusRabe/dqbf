# DQBF and Fork Resolution — Overview

This document is the theory companion to the codebase. It explains what
DQBF is, why ordinary resolution does not work for it, what *fork
resolution* adds, and how the surrounding literature fits together. Read
it before touching `provers/`.

## DQBF in one paragraph

A **Dependency Quantified Boolean Formula** is a QBF whose existential
quantifiers carry explicit dependency sets:
`∀x₁…xₙ ∃y₁(D₁) … ∃yₘ(Dₘ). φ`, where each `Dᵢ ⊆ {x₁,…,xₙ}`.
Semantically the formula is true iff there exist Boolean **Skolem
functions** `fᵢ : 𝔹^|Dᵢ| → 𝔹` such that substituting `yᵢ ↦ fᵢ(Dᵢ)`
makes `φ` a tautology in the universals. Equivalently: DQBF is the logic
of asserting "there exist Boolean functions with these specific argument
lists such that …". That is exactly the shape of **synthesis** problems,
and it is why this repository treats the Skolem functions — emitted as
AIGER circuits — as the primary output, not just a SAT/UNSAT bit.

Because the `Dᵢ` need not be linearly nested, DQBF can express non-linear
information flow (multi-player games with incomplete information) and is
**NEXPTIME-complete** [Peterson & Reif 1979], strictly harder than QBF's
PSPACE.

## Why Q-resolution is not enough

Q-resolution (resolution + universal reduction) is sound and complete for
QBF because the linear prefix totally orders dependency sets by inclusion;
universal reduction can always strip the outermost universal from a clause.
In DQBF a clause can contain existentials with **incomparable** dependency
sets — an *information fork*. Neither resolution nor universal reduction
shrinks such a clause, so Q-resolution is sound but **incomplete** for
DQBF [Balabanov–Chiang–Jiang 2014; Beyersdorff et al. 2016].

The previously known complete calculi — `∀Exp+Res` and `IR-calc` —
recover completeness by **universal expansion**: case-split a universal
`x` into two annotated copies of every clause it touches. That is
exponential in the number of universals and is what every "expansion-based"
DQBF solver (iDQ, HQS, DQBDD) ultimately does.

## Fork Resolution

Fork Resolution [Rabe 2017; revised journal version Rabe & Tentrup,
unpublished] adds one structural rule that handles information forks
directly, without enumerating universal assignments.

### The proof system

| Rule | From | Derive | Side condition |
|---|---|---|---|
| **Res** | `C₁∨ℓ`,  `C₂∨¬ℓ` | `C₁∨C₂` | — |
| **∀Red** | `C∨ℓ` | `C` | `var(ℓ)` universal, `var(ℓ) ∉ dep(C)`, `¬ℓ ∉ C` |
| **FEx** (Fork Extension) | `C₁∨C₂` | `∃x(dep C₁ ∩ dep C₂). (C₁∨x) ∧ (C₂∨¬x)` | `x` fresh |
| **SFEx** (Strong Fork Extension) | `C₁∨C₂` | `∃x((dep C₁ ∩ dep C₂)∖dep C₃). (C₃∨C₁∨x) ∧ (C₃∨C₂∨¬x)` | `x` fresh; `C₃` universal literals |

**FEx** introduces a fresh existential `x` — an *arbiter* — whose
dependency set is the **intersection** of the two halves'. Intuitively `x`
decides, using only the information common to both sides of the fork,
which side is responsible for satisfying the original clause. Soundness:
any Skolem model of the input extends to one for `x` (journal §4, Lemma 1).

### Original vs. revised paper — what changed and why

The SAT 2017 paper claimed `Res + ∀Red + FEx` is sound and refutationally
complete for all DQBF. The unpublished journal revision
([source](https://github.com/MarkusRabe/dqbf_fork_resolution_journal))
identifies a gap and repairs it:

- **The gap.** Completeness needs FEx to always make progress (strictly
  shrink some dependency set). When dependency sets form a **cycle** —
  e.g. `y₁:{x₁,x₂}`, `y₂:{x₂,x₃}`, `y₃:{x₁,x₃}` over a parity matrix —
  every binary split of a clause has one side's dependencies contained in
  the other's, so the arbiter's dependency set equals one side and nothing
  shrinks (journal §6).
- **The repair.** Two-layered:
  1. The original system *is* complete on **multi-linear normal form
     (MNF)** DQBF, where dependency sets are pairwise disjoint or
     comparable (journal §5.1).
  2. For general DQBF, **Strong Fork Extension** weakens the two new
     clauses with a chosen set `C₃` of universal literals, letting the
     arbiter drop those universals from its dependency set. Two SFEx
     applications with complementary `C₃` break any dependency cycle
     (journal Lemma `lem:elimstrongforks`). **Strong Fork Resolution =
     Res + ∀Red + SFEx** is sound and complete for arbitrary DQBF
     (journal Thm. `thm:strongsoundandcomplete`).

**This repository implements the journal version's rules.** The SAT 2017
rules are a special case (`C₃ = ∅`).

### Proof-complexity position

`∀Exp+Res` does **not** polynomially simulate Fork Resolution (journal §7;
inherits the QBF-level separation since Fork Resolution ⊇ Q-resolution).
Whether `IR-calc` simulates Fork Resolution is open.

## How the literature relates

| System / tool | Reference | Relation to Fork Resolution |
|---|---|---|
| Q-resolution | Büning–Karpinski–Flögel 1995 | Subsumed (FEx adds the missing rule); incomplete for DQBF |
| QU-resolution | Van Gelder 2012 | Incomplete for DQBF |
| LD-Q-Res, IRM-calc | Beyersdorff et al. 2016 | **Unsound** when lifted naively to DQBF |
| ∀Exp+Res | Janota & Marques-Silva 2013 | Complete via expansion; does not p-simulate Fork Res |
| IR-calc / D-IR-calc | Beyersdorff et al. 2016 | Complete annotated-clause calculus; simulation w.r.t. Fork Res open |
| **Fork Resolution** | Rabe 2017 | Complete for **MNF** DQBF |
| **Strong Fork Resolution** | Rabe & Tentrup (journal) | Complete for general DQBF; what `provers/` implements |
| dCAQE (clausal abstraction) | Tentrup & Rabe 2019 | CEGAR solver that **uses FEx as its learning rule** |
| iDQ | Fröhlich et al. 2014 | First DQBF solver; instantiation-based (expansion) |
| HQS / HQSpre | Wimmer, Scholl et al. 2015– | Expansion + elimination; emits AIGER Skolem certs |
| DQBDD | Sič 2021 | BDD-backed expansion |
| Pedant | Slivovsky et al. 2022 | Definition-extraction; emits AIGER Skolem certs |
| HQS-Henkin (DP-style) | Wimmer et al. 2021 | Variable elimination lifted to DQBF |

## Applications that motivate the encodings in `tools/`

- **Partial Equivalence Checking / incomplete-circuit BMC** —
  Gitina et al. 2013; Scholl et al. 2018. Each black-box output becomes an
  existential whose dependency set is exactly that black box's inputs; PEC
  and DQBF are polynomially equivalent. → `tools/bmc2dqbf/`.
- **Bounded reactive synthesis from LTL** — Faymonville, Finkbeiner,
  Tentrup (TACAS 2017; BoSy, CAV 2017). Universally quantify source state,
  target state, and environment input; existentially quantify the system's
  transition/output functions with restricted dependencies. DQBF gives an
  encoding linear in the state bound where QBF is quadratic.
  → `tools/ltlsynth2dqbf/`.
- **Quantified bit-vectors / function synthesis** — bit-blasting a QBVF
  with a linear prefix yields plain QBF; DQBF adds power exactly when the
  source has uninterpreted function symbols or non-linear dependencies.
  That gap is what the **EQFOB** language (`tools/eqfob/`) targets.

## Annotated bibliography

- **Rabe, M. N.** *A Resolution-Style Proof System for DQBF.* SAT 2017,
  LNCS 10491, 314–325.
  [doi:10.1007/978-3-319-66263-3_20](https://link.springer.com/chapter/10.1007/978-3-319-66263-3_20).
  Original Fork Resolution paper.
- **Rabe, M. N., Tentrup, L.** *Solving DQBF without Universal Expansion.*
  Unpublished journal revision.
  [github.com/MarkusRabe/dqbf_fork_resolution_journal](https://github.com/MarkusRabe/dqbf_fork_resolution_journal).
  Adds the dependency-cycle counterexample, MNF restriction, and Strong
  Fork Extension. **Authoritative for this repo.**
- **Tentrup, L., Rabe, M. N.** *Clausal Abstraction for DQBF.* SAT 2019.
  [arXiv:1808.08759](https://arxiv.org/abs/1808.08759). dCAQE solver:
  CAQE-style abstraction using FEx as the learning step.
- **Beyersdorff, O., Chew, L., Schmidt, R., Suda, M.** *Lifting QBF
  Resolution Calculi to DQBF.* SAT 2016.
  [arXiv:1604.08058](https://arxiv.org/abs/1604.08058). Maps the QBF
  proof-complexity landscape onto DQBF; the baseline Fork Resolution is
  positioned against.
- **Balabanov, V., Chiang, H.-J. K., Jiang, J.-H. R.** *Henkin Quantifiers
  and Boolean Formulae: A Certification Perspective of DQBF.* TCS 2014.
  First proof that Q-resolution is incomplete for DQBF.
- **Fröhlich, A., Kovásznai, G., Biere, A., Veith, H.** *iDQ:
  Instantiation-Based DQBF Solving.* POS@SAT 2014.
  [paper](https://easychair.org/publications/paper/PRV). First practical
  DQBF solver.
- **Scholl, C., Wimmer, R.** *Dependency Quantified Boolean Formulas: An
  Overview of Solution Methods and Applications.* SAT 2018 (invited).
  [PDF](https://abs.informatik.uni-freiburg.de/papers/2018/SW_2018.pdf).
  Survey; best entry point to applications.
- **Wimmer, R., Scholl, C., Becker, B., et al.** *Davis and Putnam Meet
  Henkin: Solving DQBF with Resolution.* SAT 2021.
  [doi:10.1007/978-3-030-80223-3_4](https://link.springer.com/chapter/10.1007/978-3-030-80223-3_4).
- **Wimmer, R., Reimer, S., Scholl, C., Becker, B., et al.** *Skolem
  Functions for DQBF.* ATVA 2016. Certificate format we adopt.
- **Sič, J.** *DQBDD: An Efficient BDD-Based DQBF Solver.* SAT 2021.
  [doi:10.1007/978-3-030-80223-3_36](https://link.springer.com/chapter/10.1007/978-3-030-80223-3_36).
- **Slivovsky, F., et al.** *Pedant.* SAT 2022.
  [doi:10.4230/LIPIcs.SAT.2022.20](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2022.20).
  Definition-extraction solver; ships a Skolem-cert verifier we mirror.
- **Gitina, K., Reimer, S., Sauer, M., Wimmer, R., Scholl, C., Becker, B.**
  *Equivalence Checking of Partial Designs Using DQBF.* ICCD 2013.
- **Faymonville, P., Finkbeiner, B., Tentrup, L.** *Encodings of Bounded
  Synthesis.* TACAS 2017.
  [doi:10.1007/978-3-662-54577-5_20](https://link.springer.com/chapter/10.1007/978-3-662-54577-5_20).
- **Faymonville, P., Finkbeiner, B., Rabe, M. N., Tentrup, L.** *BoSy: An
  Experimentation Framework for Bounded Synthesis.* CAV 2017.
  [arXiv:1803.09566](https://arxiv.org/abs/1803.09566).
- **Peterson, G., Reif, J.** *Multiple-Person Alternation.* FOCS 1979.
  NEXPTIME-completeness of DQBF.
- **Finkbeiner, B., Schewe, S.** *Uniform Distributed Synthesis.* LICS
  2005. Origin of the term "information fork".

## Primary source materials

- The original SAT 2017 paper appears in LNCS 10491 at pp. 314–325
  ([doi:10.1007/978-3-319-66263-3_20](https://link.springer.com/chapter/10.1007/978-3-319-66263-3_20)).
  A local copy is kept at `docs/references/local/rabe_sat2017_forkres.pdf`
  (not committed; see `docs/references/local/README.md`).
- The journal revision's LaTeX source is mirrored under
  `docs/references/fork_resolution_journal/`; `main.tex` is the canonical
  rule definitions.
