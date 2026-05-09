# Verifier risk model — Python (`tools/verify/`)

Companion to `tools/verify_rs/RISKS.md` (the Rust verifier's risk
model). This document covers the *Python* verifier specifically: which
side-conditions it checks, which it doesn't, and whether each gap is
exploitable. It also records the cross-implementation disagreements
found during the Rust verifier build, with a classification for each.

The guiding principle is **fail-INVALID, never fail-silent**: if
anything goes wrong — bad input, parse error, missing file, SAT-solver
crash, unexpected exception — the verifier must report something other
than `VALID`. "Couldn't verify" is not "verified".

## Background: the `f672573` episode

Commit `f672573` (2026-05-06) changed the FEx/SFEx prefix-extension
call in `tools/verify/unsat.py:119` from `g.with_existential(...)` to
`g.add_existential(...)`. The commit message calls it a typo fix. It
was actually a *call-site rename* between two `Formula` types that did
not share a method name:

- `tools.verify.formats.Formula` — the type `cli.py` builds and passes
  to `verify_proof`. Had `with_existential`.
- `core.formula.Formula` — the type `scripts/unsat_cert_mapping.py`
  passes (it imports `Formula` from `core`, not `tools.verify`). Has
  `add_existential`.

Before `f672573`: the FEx/SFEx path crashed (`AttributeError`) for
callers using `core.formula.Formula`. After `f672573`: it crashed for
callers using `formats.Formula` — i.e. **the CLI path the bench
harness uses**, and `tools/verify/unsat_test.py`. Either way the
FEx/SFEx side-conditions were never exercised by the bench harness:
the verifier crashed instead of returning a verdict. The bench's
`_verify_one` records a crash (exit code other than 0/1/2/3) as
`"error"`, not `"valid"`, so this was *fail-loud*, not fail-open — but
it also meant any FEx-using `.frp` proof was never marked `valid`,
which is a silent under-count.

The proper fix (commit accompanying this note) renames the *method* in
`formats.py` to `add_existential`, matching `core.formula.Formula`, so
both Formula types satisfy the call. The regression test
`test_f672573_regression_fex_returns_not_raises` in
`tools/verify/unsat_test.py` pins this: it verifies an FEx proof and
asserts the result is a `bool`, so an `AttributeError` here would be a
visible test failure rather than a silent crash in CI.

**Lesson:** the proof checker is duck-typed against any `Formula` with
the right methods, and there are *two* such types in the repo (the
self-contained `formats.Formula` and the shared `core.formula.Formula`).
Until they share a base class or a `Protocol`, the only protection is
test coverage of the FEx/SFEx path with both types. The current test
file uses `formats.Formula` (matching `cli.py`); `scripts/
unsat_cert_mapping.py` uses `core.formula.Formula` and is run as part
of the worked-example documentation.

## Per-rule side-conditions

For each rule, what the verifier checks and what it doesn't. Tests are
in `tools/verify/unsat_test.py`; the Rust verifier's equivalents are
in `tools/verify_rs/RISKS.md` (`A1-A3`, `R1-R7`, `D1-D6`, `F1-F10`,
`S1-S4`, `C1-C10`).

### Axiom

Checked: the claimed clause is in `g.clauses` (set equality).

Not checked: spurious `premises` field. **Classification: benign
metadata leniency** — the field is ignored, the verdict is unchanged.
Pinned by `test_lenient_axiom_with_spurious_premises`. The Rust
verifier rejects this; both directions are sound (the Rust verifier
is stricter, which is the safe direction for cross-checking).

### Resolution (`res`)

Checked: exactly two premises in range; pivot present in both with
opposite polarity; resolvent not a tautology; the claimed clause is
either the resolvent or a sound ∀-reduction of it.

The last point — accepting a `res` step whose claimed clause has had
universals dropped — is the **fused-res-∀Red convention**. The `.frp`
emitter (frust's `proof_emit.rs`) emits Q-resolution steps where the
∀-reduction is implicit in the result clause. The verifier's
`_is_ureduction(g, r, c)` accepts `c ⊆ r` with each dropped lit
satisfying the ∀-red side-condition. **Classification: spec
ambiguity** — the journal phrases `Res` and `∀Red` as separate rules;
the `.frp` format fuses them; both verifiers now accept the fused form
and check it exactly. This should be noted in the journal revision so
a third independent implementation isn't surprised.

Not checked: a `res` step that *doesn't* perform any ∀-reduction is
indistinguishable from one that does — the verifier checks the result,
not the mechanism. Benign.

### ∀-reduction (`ured`)

Checked: exactly one premise; result ⊆ premise; each dropped literal
is universal, not in the existential-dep set of the *result*, and its
negation is not in the premise.

Not checked: a no-op `ured` (result == premise) is accepted. Sound
(drops the empty set), but a confused prover would produce it.
**Classification: benign metadata leniency** — pinned by
`test_lenient_ured_noop`. The Rust verifier rejects.

### Fork extension (`fex`) / strong (`sfex`)

Checked (after `f672573` and the follow-up rename): `part ⊆ src`;
claimed clause is one of the two halves; `fresh` not ≤ `n_vars`, not
already an existential, not a universal; sibling re-use only with the
identical `(premise, part, c3, rule)` signature; `dep(fresh)` recorded
as `clause_dep(C₁) ∩ clause_dep(C₂) ∖ var(c3)`. SFEx: `c3` must be
all-universal.

Not checked: nothing material. The dep accounting is the most
important part — too-large dep makes downstream `ured` over-permissive
(unsound, F7), too-small makes it under-permissive (incomplete, F8).
Both are covered by the `test_fex_dep_*` tests.

### SAT certificate (`.aag`)

Checked (in `tools/verify/sat.py`): each output's input cone ⊆ that
existential's dep set (via `encode_verification`'s dep-violation
collection); the substitution miter is UNSAT (via an external SAT
solver).

Not checked sufficiently: **the input symbol-table check**. The Rust
verifier rejects an `.aag` where `i<k> u<j>` names a non-universal `j`
*before* doing the cone check. The Python verifier's cone check is
done against the AIGER inputs by position, not by symbol — if the
symbol `i0` claims `u9` and `9` is not a universal, the cone check
either (a) fails to find the universal, which surfaces as a violation,
or (b) passes vacuously when the output is constant (no cone to
check). Case (b) is the gap the Rust verifier found.
**Classification: low-severity exploitable gap** — a malicious cert
could mislabel an input behind a constant output and skip the cone
check. In practice the substitution miter would still fail (the cert
function is a constant, so unless the formula is genuinely SAT with
that constant, the miter is SAT and the verdict is INVALID), so the
SAT check is a backstop. Documented but not fixed in this commit (the
fix touches `encode_verification` and needs careful testing of the
varmap; queued).

## Error-handling audit

Both verifiers were audited for fail-open paths. Summary:

| where | path | before | after |
|---|---|---|---|
| `cli.py` `unsat_cmd` | `verify_proof` raises | uncaught traceback (exit 1, treated as error) | unchanged — exit 1 is safe; a crash and an INVALID are both non-VALID. |
| `cli.py` `sat_cmd` | `solve_cnf` returns `(None, None)` | exit 3 ("skipped") | unchanged — a crashed/missing SAT backend cannot say VALID. |
| `sat.py` `solve_cnf` | external solver hangs | `subprocess.run` waits forever | **fixed** — 300 s timeout returns `(None, None)` (→ exit 3). |
| `sat.py` `solve_cnf` | external solver exits with non-standard code | `(None, None)` | unchanged. |
| `unsat.py` | malformed `.frp` step | `load_proof` raises | unchanged — raise propagates to a non-zero exit. |
| Rust `sat.rs` | SAT solver exit not 10/20/UNSAT | `Verdict::Invalid` | safe. |
| Rust `sat.rs` | SAT solver prints `s UNSATISFIABLE` but crashes | `Verdict::Valid` (text match wins) | **flagged, not fixed** — low risk (SAT solver is trusted dependency, not adversarial input), but check exit code first. |
| Rust `main.rs` | parse error in any input | `INVALID` + exit 1 | safe — every error path is fail-INVALID. |
| Rust | SAT solver hangs | `Command::output()` no timeout | **flagged, not fixed** — same as Python before this commit; the harness has its own timeout. |

## Cross-implementation disagreement classification

From the Rust verifier's cross-check (`tools/verify_rs/RISKS.md` §
"cross-implementation"; the Rust verifier never accepts what the
Python verifier rejects, only vice versa):

| disagreement | direction | classification |
|---|---|---|
| axiom with spurious `premises` | Python lenient, Rust strict | (a) benign metadata leniency — document, don't change |
| no-op `ured` | Python lenient, Rust strict | (a) benign metadata leniency — document, don't change |
| input symbol mislabel + constant output | Python lenient, Rust strict | (b) low-severity exploitable gap — fix queued (see SAT certificate section) |
| fused res+∀Red | both accept; convention not in journal | (c) spec ambiguity — note for journal revision |

Going forward, **any new cross-check disagreement must be classified
into (a)/(b)/(c) and recorded here**. The dangerous direction —
Rust=VALID, Python=INVALID — has no instances and `cross_check_test.sh`
fails hard on it.

## Test inventory (Python verifier)

`tools/verify/unsat_test.py` (41 tests):
- 7 valid-proof tests, including the `f672573` regression and the
  fused-res-∀Red convention.
- 28 rejection tests, one per side-condition (Res, ured, FEx, SFEx).
- 2 documented-leniency tests (axiom premises, ured no-op).
- 4 dep-accounting tests (intersection used, too-small caught,
  SFEx subtraction, sibling re-use).

Adversarial corpus is shared with `tools/verify_rs/tests/adversarial/`;
`tools/verify_rs/cross_check_test.sh` runs both verifiers on every
case and fails on a Rust=VALID/Python=INVALID disagreement.
