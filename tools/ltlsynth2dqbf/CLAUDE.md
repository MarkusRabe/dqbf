# tools/ltlsynth2dqbf/ — LTL Bounded Synthesis → DQBF

Encode bounded reactive synthesis (find an `n`-state Mealy machine
realizing an LTL spec) as a DQBF.

> **Soundness restriction**: the current encoding is **safety-only**
> (G, X, R). For specs containing F/U/W, `encode()` raises
> `EncodingNotSound`. See the FFT'17 section below for why.

## Current encoding (unroll-lasso, no automaton — **safety fragment only**)

`spot`/`syfco` are not available in this environment, so the encoder
ships an **automaton-free fallback**: unroll a single ∀-quantified
input trace of length `k`, build the system run via existential δ/λ
functions (with Ackermann congruence enforcing they are functions of
`(state, input)` only), and assert the spec holds in ∀-loop bounded
LTL semantics.

**Why safety-only**: the lasso closes on system-state equality
(`s_k = s_L`), so the input word is `i_0..i_{k-1}(i_L..i_{k-1})^ω` —
the system effectively only sees periodic traces. For any spec with a
`GF p` antecedent the system can choose `s_k = s_{k-1}` (single-step
loop), making the antecedent `p_{k-1} ∧ ¬p_{k-1} = false` and the
implication vacuously true. This was observed as DQBF-SAT for the
unrealizable `CheckAlarm`/`CheckTime` specs.

## The correct encoding (FFT'17, arXiv:1803.09566 §4)

`∃δ,λ,θ. ∀s,s',q,q',i. (consistency ∧ θ-monotone on rejecting q)`
where `q` ranges over states of the **universal co-Büchi automaton of
¬φ** and θ is a ranking annotation. The ranking is what collapses "all
ω-words" into a per-transition well-foundedness check. Building the
automaton requires `spot` or `ltl3ba` — install one and replace
`encode()` with the §4 construction to lift the safety restriction.

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
