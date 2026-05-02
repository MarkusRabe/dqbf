# tests/integration/ — end-to-end correctness

A curated set of small instances with **known** SAT/UNSAT status. Every
prover and every encoder must agree with the oracle on every instance,
and every SAT result must survive `tools/verify/`.

## Layout

```
tiny/             hand-written DQDIMACS, ≤20 vars
manifest.json     [{"path", "expected"}]
test_e2e.py       parametrized pytest: run prover → check result →
                  verify the .aag / .frp via tools/verify (file interface)
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

- [x] `tiny/` seed set.
- [x] `test_e2e.py` driving `provers/forkres` over `tiny/`.
- [x] Wire `tools/verify/` into both branches via the file interface.
- [ ] Differential test once the Rust prover exists.
- [ ] Nightly CI job over a slice of `benchmarks/test/dqbf_qbflib/`.
