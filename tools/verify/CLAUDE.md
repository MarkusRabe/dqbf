# tools/verify/ — independent solution checkers

## Self-containment (the trust boundary)

**`tools/verify/` has zero dependencies on the rest of this repository.**
Every non-test file here imports only:

- other files under `tools/verify/`
- the Python standard library
- a short whitelist of external solver packages (`click`, `pysat`)

In particular it does **not** import `core/`, `provers/`, or anything
else in this tree. The DQDIMACS / AIGER / `.frp` readers it needs are
duplicated locally in `formats.py`, in deliberately minimal form.

This means you can audit the four files

```
formats.py   data-format readers (Formula, Aag, Proof)
unsat.py     proof-trace replay
sat.py       AIGER substitution → DIMACS CNF + var-map; optional SAT backend
cli.py       dqbf-verify {sat,unsat}
```

(~450 lines total) once, and then iterate freely on `provers/` knowing
that no prover change can alter what the verifier accepts.

`boundary_test.py` enforces this at CI time: it AST-walks every
non-test file under `tools/verify/` and **fails** if any import is not
stdlib, `tools.verify.*`, or in the whitelist.

## SAT certificates

`dqbf-verify sat FORMULA.dqdimacs CERT.aag -o verify.cnf --map verify.map.json [--solve]`

Reads the DQBF and an AIGER bundle (inputs `u<id>`, outputs `e<id>`).
Performs a structural dependency check (each `e<y>`'s input cone ⊆
`deps(y)`), then emits a DIMACS CNF whose **UNSAT ⇒ certificate valid**
plus a JSON variable map. With `--solve`, runs the first available SAT
backend — PySAT if importable, otherwise `cadical`/`kissat`/`satch` on
PATH, otherwise `third_party/{kissat/build/kissat,satch/satch}` directly
— and prints `VALID`/`INVALID`, decoding any counterexample model via
the var-map.

## UNSAT certificates

`dqbf-verify unsat FORMULA.dqdimacs PROOF.frp`

Replays a fork-resolution trace step by step. Rule checks (Res, ∀Red,
FEx, SFEx) are implemented locally; nothing is shared with `provers/`.

## Contract with provers

The **only** contract is on-disk files: DQDIMACS, `.aag`, `.frp`. The
verifier and the provers do not share Python types. Cross-cutting
"prover output passes verification" tests live in
`tests/integration/test_e2e.py` and go through that file interface.

## References

- AIGER spec: https://fmv.jku.at/aiger/FORMAT
- Substitute-then-SAT precedent: Pedant `certifyModel.py`
  (https://github.com/fslivovsky/pedant-solver)
- Wimmer et al., *Skolem Functions for DQBF*, ATVA 2016.
