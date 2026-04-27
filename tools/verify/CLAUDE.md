# tools/verify/ — certificate checker

Independently check that a claimed solution actually satisfies the DQBF.

## Purpose

Given a DQDIMACS formula Φ and an AIGER circuit bundle that maps each
existential variable *y* to a combinational circuit over exactly its
declared dependency set *D(y)*:

1. **Dependency check** — every Skolem circuit's inputs ⊆ *D(y)*.
2. **Validity check** — substitute the circuits into the matrix, leaving a
   purely universal formula; assert it is a tautology by SAT-solving its
   negation.

On UNSAT instances, separately replay a fork-resolution refutation trace
line by line and confirm it derives the empty clause.

## Interface

```
dqbf-verify sat   FORMULA.dqdimacs CERT.aag   → exit 0 iff valid
dqbf-verify unsat FORMULA.dqdimacs PROOF.frp  → exit 0 iff valid
```

## References

- AIGER spec: https://fmv.jku.at/aiger/FORMAT
- py-aiger / py-aiger-cnf: https://github.com/mvcisback/py-aiger
- Prior art: Pedant's `certifyModel.py`
  (https://github.com/fslivovsky/pedant-solver) does exactly the
  substitute-and-SAT-check flow; mirror its semantics so certificates are
  interchangeable.
- Wimmer et al., *Skolem Functions for DQBF*, ATVA 2016.

## Plan

- [ ] AIGER bundle format: one `.aag` with symbol table mapping output
      names ↔ existential var IDs; document in
      `docs/references/certificate_format.md`.
- [ ] `verify/sat.py`: load AIG (py-aiger) → substitute → Tseitin →
      hand to a SAT solver (PySAT).
- [ ] `verify/unsat.py`: `.frp` trace replayer reusing
      `provers/python/forkres/rules.py` so the rule semantics are defined
      in exactly one place.
- [ ] Hook both into `tests/integration/` so every prover SAT/UNSAT
      result is independently re-checked.
