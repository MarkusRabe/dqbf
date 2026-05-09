# Risk-factor analysis for the Rust DQBF verifier

This document was written **before** implementing any rule check. Each
risk below is a way an *incorrect* certificate could try to slip
through the verifier, plus the test that prevents it. The adversarial
corpus in `tests/adversarial/` has one mutated cert per risk.

A verifier that accepts an incorrect proof is worse than no verifier:
it manufactures false confidence. Accordingly the bias here is
**reject-on-doubt** — any malformed, unparseable, ambiguous, or
out-of-range input must produce `INVALID`, never a panic and never
`VALID`.

## Risks shared across all UNSAT proof rules

| # | risk | description | test |
|---|------|-------------|------|
| U1 | premise out of range | `premises` index ≥ current step count or < 0 | `adv_premise_oob` |
| U2 | forward premise | `premises` index ≥ own step index (refers to a not-yet-derived clause) | `adv_premise_forward` |
| U3 | claimed clause ≠ derived clause | step's `clause` field disagrees with what the rule actually produces from the premises | `adv_wrong_resolvent`, `adv_wrong_ured`, `adv_wrong_fex_left/right` |
| U4 | no empty clause | proof has no `()` step yet verifier returns VALID | `adv_no_refutation` |
| U5 | unknown rule name | `rule` not in the allowed set | `adv_unknown_rule` |
| U6 | empty proof | zero steps | `adv_empty_proof` |
| U7 | duplicate / unsorted literals | `clause` field with `[1, 1]` or `[2, 1]`; verifier must canonicalise before comparing, not compare raw arrays | `adv_dup_lits`, `adv_unsorted_lits` |
| U8 | tautological claimed clause | step's `clause` contains `l` and `-l` | `adv_taut_clause` |
| U9 | integer overflow on var ids | var id near `i32::MAX`; sign flips or hash collisions | `adv_huge_var` (must reject cleanly, not crash) |
| U10 | malformed JSON | truncated file, missing fields, wrong types | `adv_bad_json_*` |

## Axiom

| # | risk | description | test |
|---|------|-------------|------|
| A1 | not in input matrix | `clause` not equal (as a set) to any input clause | `adv_axiom_not_in_matrix` |
| A2 | superset of an input | a strict superset of an input clause is *not* an axiom | `adv_axiom_superset` |
| A3 | premise on axiom | axiom carries spurious premises (suspicious; reject) | `adv_axiom_with_premise` |

## Resolution (`res`)

`C₁∨ℓ` and `C₂∨¬ℓ` derive `C₁∨C₂`, which must not be a tautology.

| # | risk | description | test |
|---|------|-------------|------|
| R1 | wrong pivot | `pivot` is not present in either premise (or both contain it positively) | `adv_res_wrong_pivot` |
| R2 | pivot missing | `pivot` field absent or null | `adv_res_no_pivot` |
| R3 | not exactly two premises | 0, 1, or ≥3 premises | `adv_res_one_premise` |
| R4 | resolvent is tautological | literal `m` and `¬m` both survive the merge | `adv_res_taut_resolvent` |
| R5 | claimed clause adds literals | `clause` contains literals not in either premise | `adv_res_extra_lit` |
| R6 | claimed clause drops literals | `clause` is a strict subset of the true resolvent (silent strengthening) | `adv_res_missing_lit` |
| R7 | pivot polarity wrong | both premises contain `+pivot` (or both `-pivot`) | `adv_res_same_polarity` |

## Universal reduction (`ured`)

Drop universal literal `ℓ` from `C∨ℓ` iff `var(ℓ)` is universal,
`var(ℓ) ∉ dep(C)`, and `¬ℓ ∉ C`. `dep(C)` = (universal vars of C) ∪
∪{dep(y) : y existential in C}. Multiple universals may be dropped in
one step (the difference is a set of universal lits each individually
satisfying the side condition w.r.t. the *result* clause).

| # | risk | description | test |
|---|------|-------------|------|
| D1 | dropped a non-universal | the removed literal's var is existential | `adv_ured_drop_existential` |
| D2 | dropped a depended-on universal | removed `u` but some existential `y` in C has `u ∈ dep(y)` | `adv_ured_depended` |
| D3 | dropped the wrong polarity | `¬ℓ` was in C (would change satisfiability) | `adv_ured_wrong_polarity` |
| D4 | added a literal | `clause` is not a subset of the premise | `adv_ured_added_lit` |
| D5 | nothing dropped | `clause` equals premise — vacuous step (reject; signals confusion) | `adv_ured_noop` |
| D6 | dropped a universal still in the result via another existential | drop `u` from a clause where dropping changes which existentials depend on `u` (must check against the *post-drop* clause's dep set, not pre-drop) | `adv_ured_self_witness` |

## Fork Extension (`fex`)

From `C` derive `C₁∨x` and `C₂∨¬x`, where `C₁∪C₂ = C`, `x` fresh,
`dep(x) = dep(C₁) ∩ dep(C₂)`. The `.frp` step claims one half; the
`part` field gives `C₁`. Both halves must be checked.

| # | risk | description | test |
|---|------|-------------|------|
| F1 | `part` not a subset of premise | `C₁ ⊄ C` | `adv_fex_part_not_subset` |
| F2 | `part = C` or `part = ∅` | degenerate split (one half empty + unit fork) — accept only if the other side really has the right form; unit `(x)` with empty `C₂` is questionable, must check side-condition exactly | `adv_fex_empty_part` |
| F3 | `fresh` not fresh | `x` already exists in the original prefix or a prior step | `adv_fex_not_fresh` |
| F4 | `fresh` collides with later FEx | two FEx steps reuse the same `fresh` id | `adv_fex_collide` |
| F5 | wrong `fresh` polarity in claimed clause | claimed clause has `-x` but `clause = C₁∨x` (left side gets `+x`, right gets `-x`) | `adv_fex_wrong_polarity` |
| F6 | claimed clause neither half | claimed clause is some other set | `adv_fex_neither_half` |
| F7 | `dep(x)` accounting | the verifier must add `x` to its own prefix with the correct dep set so that downstream `ured` checks are correct. A proof that exploits a too-large `dep(x)` (e.g. union instead of intersection) would let it survive a `ured` it shouldn't | `adv_fex_then_bad_ured` |
| F8 | `dep(x)` accounting (too small) | conversely, if the verifier records `dep(x)` too small, a downstream `ured` would *falsely* drop a universal `x` actually depends on | covered by `adv_fex_then_bad_ured` (mutate the other direction) |
| F9 | missing `part` field | `part` absent | `adv_fex_no_part` |
| F10 | premise must be a single derived clause | not 1 premise | `adv_fex_two_premises` |

## Strong Fork Extension (`sfex`)

Like FEx, but with `c3` (universal lits) added to both halves and
`dep(x) = (dep(C₁) ∩ dep(C₂)) \ var(c3)`.

| # | risk | description | test |
|---|------|-------------|------|
| S1 | `c3` contains an existential | `c3` must be all-universal | `adv_sfex_c3_existential` |
| S2 | `c3` not in claimed clause | the extra lits must actually appear in the result | `adv_sfex_c3_missing` |
| S3 | `dep(x)` does not subtract `var(c3)` | downstream `ured` exploits too-large dep | `adv_sfex_dep_too_big` |
| S4 | `c3` empty makes it degenerate to FEx | accept (FEx is a special case) — but ensure the check still applies; *not* a separate adversarial case |

## SAT certificate (.aag)

| # | risk | description | test |
|---|------|-------------|------|
| C1 | output cone leaks | `e<y>`'s gate cone reads an input `u<i>` with `i ∉ dep(y)` | `adv_sat_dep_leak` |
| C2 | output map mismatch | `o<k> e<y>` symbol points at the wrong existential (or a non-existential) | `adv_sat_wrong_output` |
| C3 | input map mismatch | `i<k> u<j>` points at a non-universal | `adv_sat_wrong_input` |
| C4 | missing existential | `.aag` defines fewer outputs than there are (live) existentials | `adv_sat_missing_output` |
| C5 | wrong miter polarity | encoding `¬(formula[exist:=cert])` requires Tseitin'ing the *negation* of every clause; getting this wrong inverts the verdict | `adv_sat_inverted` (a certificate for the *wrong* function that satisfies `¬φ` instead) |
| C6 | constant-fold gate to wrong constant | AIGER lit 0 = false, 1 = true; a parser that swaps them silently inverts every gate | `adv_sat_const_swap` (encode constant cert with inverted constant) |
| C7 | unconstrained universal | a universal that doesn't appear in the matrix still must be a circuit input, or the cone check on existentials referencing it crashes | `adv_sat_unused_universal` (cert reads an input that isn't a universal) |
| C8 | gate cycle | a `.aag` with a structural cycle (`g₁ = g₂ ∧ x`, `g₂ = g₁ ∧ y`); naive recursion stack-overflows | `adv_sat_cycle` |
| C9 | gate references undefined lit | gate input lit > 2*max_var | `adv_sat_oob_gate` |
| C10 | header lies | `aag M I L O A` header inconsistent with body | `adv_sat_bad_header` |

## Cross-implementation risks

| # | risk | description | test |
|---|------|-------------|------|
| X1 | tautology-of-resolvent check timing | Some implementations check tautology before merge, some after. The spec checks the *result*. | `adv_res_taut_resolvent` covers this |
| X2 | dep(C) computed against original prefix vs. extended prefix | After an FEx, the prefix has grown. `dep(C)` for a clause containing the fresh var must use the *extended* prefix. | `adv_fex_then_bad_ured` |
| X3 | clause comparison semantics | sets vs. sorted-vecs vs. raw arrays; both implementations must compare as sets | `adv_unsorted_lits`, `adv_dup_lits` |
| X4 | empty `clause` in non-final step | an empty clause derived early should make the rest of the proof dead but still acceptable (the proof *is* a refutation as soon as ⊥ appears) — both verifiers must agree | `valid_early_empty` (a *valid* case, included to pin down behaviour) |
| X5 | Formula type duck-typing | `tools/verify/unsat.py` accepts any `Formula` with the right methods; the repo has two such types (`tools.verify.formats.Formula` and `core.formula.Formula`). They must share method names or the proof checker silently crashes (`f672573` episode). | `tools/verify/unsat_test.py::test_f672573_regression_fex_returns_not_raises` |
| X6 | error path returns VALID | any code path that hits an error (parse, missing file, SAT-solver crash) must not fall through to a VALID verdict. The Rust verifier has no such path; the Python verifier's `solve_cnf` returns `(None, None)` on error → exit 3 ("skipped"), never VALID. | error-path tests in both verifiers |
| X7 | SAT solver output parse | the Rust verifier prefers the `s UNSATISFIABLE`/`s SATISFIABLE` text over the exit code; a crashed solver that emitted partial output could mislead it. Low risk (the SAT solver is a trusted dependency, not adversarial input), but check the exit code first. | flagged, not yet tested |
| X8 | SAT solver hangs | both verifiers shell out to a SAT solver without a timeout in the `cross_check_test.sh` path; the bench harness wraps in its own timeout, but a direct invocation can hang. | Python `solve_cnf` now has a 300 s timeout; Rust still doesn't. |

## Cross-check disagreement classification

The cross-check (`cross_check_test.sh`) asserts the dangerous
direction never happens: rust=VALID, python=INVALID has zero
instances. The opposite direction (python=VALID, rust=INVALID) has
three instances; each is classified per `docs/notes/verifier_risks.md`:

| disagreement | classification |
|---|---|
| axiom with spurious `premises` (A3) | (a) benign metadata leniency — Python ignores the field; Rust rejects. Both sound. |
| no-op `ured` (D6) | (a) benign metadata leniency — Python accepts (drops empty set); Rust rejects (suspicious). Both sound. |
| input symbol mislabel + constant output (C3) | (b) low-severity exploitable gap in Python — cone check passes vacuously when the output is constant. Rust rejects the symbol up front. The Python miter check is a backstop. Fix queued. |
| fused res+∀Red | (c) spec ambiguity — both verifiers accept the `.frp` emitter's Q-resolution convention. Note for the journal revision. |

## Test inventory

- `tests/rules_test.rs`: per-rule positive (valid step accepted) and
  negative (each risk above) unit tests using inline Step structs.
- `tests/formats_test.rs`: parse + roundtrip for DQDIMACS, AIGER, .frp.
  Includes degenerate inputs (empty file, header-only, missing zeros).
- `tests/adversarial/`: one file per `adv_*` named above, in the form
  `<base>.dqdimacs` + `<base>.<adv_id>.frp` (or `.aag`). The harness
  asserts `dqbf-verify-rs` returns INVALID *and* the Python verifier
  agrees.
- `cross_check_test.sh`: runs both verifiers on the entire valid +
  adversarial corpus and diffs the verdicts. Any disagreement is a
  hard failure.

Total: 10 shared + 3 axiom + 7 res + 6 ured + 10 fex + 3 sfex
+ 10 sat + 4 cross = **53 named risks**, ≥**38 adversarial cases**
(some risks share a case and some are positive cases used for
calibration), plus the unit tests.
