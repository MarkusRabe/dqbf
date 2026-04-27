# tools/verify/ — independent solution checkers

**Design principle:** simple and reusable across provers. These files
are the trusted base for the improvement loop — they import only from
`core/` (data formats), never from `provers/`. A prover may be rewritten
for speed without touching anything here.

## SAT certificates

`dqbf-verify sat FORMULA.dqdimacs CERT.aag -o verify.cnf --map verify.map.json`

Reads the original DQBF and an AIGER bundle (one combinational AIG;
inputs named `u<id>` for universals, outputs named `e<id>` for
existentials). Emits:

- `verify.cnf` — a DIMACS CNF over fresh variables. **UNSAT ⇒
  certificate valid.** Hand it to any SAT solver.
- `verify.map.json` — `{universals, existentials, aiger_gates,
  violated_clause}` mapping source-level names to DIMACS IDs, so a
  satisfying assignment (= a counterexample to the cert) can be read
  back as "universal assignment ū makes clause i false".

Before encoding, a **structural dependency check** confirms each
`e<y>`'s cone of influence touches only `u<x>` with `x ∈ deps(y)`; any
violation is reported and exits 2.

This is prover-agnostic: any solver that emits AIGER Skolem functions
(HQS, Pedant, our forkres) plugs in.

## UNSAT certificates

`dqbf-verify unsat FORMULA.dqdimacs PROOF.frp`

Replays a fork-resolution trace step by step. The rule checks
(resolution, ∀-reduction, FEx, SFEx) are **re-implemented here** —
nothing is imported from `provers/forkres/`. Exit 0 = valid, 1 =
invalid.

The trace format is `core/proof_trace.py` (JSON list of `Step`s). Any
prover that searches in the fork-resolution calculus can emit it.

## Trusted base

`core/{formula,dqdimacs,aiger,proof_trace}.py` (data) +
`tools/verify/{sat,unsat}.py` (~250 lines total). Audited once; not
touched by the improvement loop.

## References

- AIGER spec: https://fmv.jku.at/aiger/FORMAT
- Prior art for the substitute-then-SAT approach: Pedant
  `certifyModel.py` (https://github.com/fslivovsky/pedant-solver).
- Wimmer et al., *Skolem Functions for DQBF*, ATVA 2016.
