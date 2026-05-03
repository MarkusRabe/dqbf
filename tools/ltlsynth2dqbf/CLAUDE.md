# tools/ltlsynth2dqbf/ — LTL Bounded Synthesis → DQBF

Encode bounded reactive synthesis (find an `n`-state Mealy machine
realizing an LTL spec) as a DQBF.

## Current encoding (unroll-lasso, no automaton)

`spot`/`syfco` are not available in this environment, so the encoder
ships an **automaton-free fallback**: unroll a single ∀-quantified
input trace of length `k`, build the system run via existential δ/λ
functions (with Ackermann congruence enforcing they are functions of
`(state, input)` only), and assert the spec holds in ∀-loop bounded
LTL semantics.

| Vars | Quant | Deps |
|---|---|---|
| `L_t` (loop pos) | ∀ | — |
| `i_{t,j}` | ∀ | — |
| `o_{t,j}` | ∃ | `i_{0..t}` |
| `s_{t,j}` | ∃ | `i_{0..t-1}` |
| Tseitin / LTL aux | ∃ | all universals |

**Semantics**: SAT ⇒ REALIZABLE (sound). UNSAT at given (n,k) is
**inconclusive** — mirrors the bounded-k handling for HWMC. The runner
maps `REALIZABLE↔sat`, `UNREALIZABLE↔unsat`; a DQBF-UNSAT vs
strix-REALIZABLE is *not* a real disagreement.

## Target encoding (TACAS'17 §4 — needs `spot`)

For state bound `n`, universally quantify a **source state**, a
**target state**, and the **environment input**; existentially quantify
`δ(s,i)`, `λ(s,i)`, and an annotation `θ(s,q)`. The matrix asserts the
annotated run on the universal co-Büchi automaton of `¬φ` stays
bounded. Linear in `n` where the QBF version is quadratic. Blocked on
`spot` (LTL→co-Büchi).

## TLSF parser (`tlsf.py`)

Native, minimal. Handles: `INFO`, `MAIN { INPUTS / OUTPUTS / INITIALLY
/ PRESET / REQUIRE / ASSERT / INVARIANTS / ASSUME / GUARANTEE }`,
single-level `GLOBAL { PARAMETERS }` with integer literals, array
signals `r[n]`, and big-ops `&&[l <= i < u] body`. Anything else
(`DEFINITIONS`, nested params) raises `TlsfNotSupported`.

**Known limitation**: section-combination uses plain implication
`(∧ assumes) → (∧ guarantees)`. Specs whose assumptions reference
system outputs (e.g. `lilydemo24.tlsf`) need GR(1)-style strict
implication, which `syfco` would emit. Those specs will disagree with
strix; tracked, not a soundness bug in the DQBF encoder.

## References

- Faymonville, Finkbeiner, Tentrup. *Encodings of Bounded Synthesis.*
  TACAS 2017.
  https://link.springer.com/chapter/10.1007/978-3-662-54577-5_20
- Faymonville, Finkbeiner, Rabe, Tentrup. *BoSy.* CAV 2017.
  https://arxiv.org/abs/1803.09566
- Biere et al. *Bounded Model Checking.* (lasso LTL semantics)
- Input format: TLSF (SYNTCOMP). https://arxiv.org/abs/1604.02284

## Plan

- [x] Native TLSF parser (minimal subset; 20/20 syntcomp_legacy parse).
- [x] LTL parser → AST.
- [x] Unroll-lasso encoder; tests vs hqs on tiny specs.
- [ ] LTL → universal co-Büchi (via `spot`); switch to TACAS'17 §4.
- [ ] GR(1)-style strict implication for assumptions over outputs.
- [ ] SAT cert → `δ`/`λ` AIGER (Mealy machine extraction).
