# tests/integration/ — end-to-end correctness

A curated set of small instances with **known** SAT/UNSAT status. Every
prover and every encoder must agree with the oracle on every instance,
and every SAT result must survive `tools/verify/`.

## Layout

```
tiny/             hand-written DQDIMACS, ≤20 vars; the §6 cycle example etc.
from_eqfob/       compiled from tools/eqfob/examples/
from_competition/ a small slice of benchmarks/dqbf/ with published results
manifest.json     [{"path", "expected", "source"}]
test_e2e.py       parametrized pytest: run prover → check exit code →
                  if SAT, run dqbf-verify on the certificate
diff_provers.py   python vs rust prover differential test
```

## Conventions (mirrors cadet's `integration-tests/`)

- Expected result is in `manifest.json`; filenames may *also* carry a
  `_sat`/`_unsat` suffix for readability but the manifest is
  authoritative.
- Exit codes: `10 SAT / 20 UNSAT / 30 UNKNOWN`.
- Crash-regression cases (no expected result) pass iff the prover exits
  cleanly within timeout.

## References

- cadet integration tests:
  https://github.com/MarkusRabe/cadet/tree/master/integration-tests
- Pedant `certifyModel.py` for the verification step.

## Plan

- [ ] `tiny/` seed set: 10 SAT + 10 UNSAT + 3 crash-regression.
- [ ] `test_e2e.py` driving `provers/forkres` over `tiny/`.
- [ ] Wire `tools/verify/` into the SAT branch.
- [ ] `diff_provers.py` once Rust prover exists.
- [ ] Nightly CI job over `from_competition/`.
