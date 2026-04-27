# tools/

Everything that is **not a prover**: input languages, encoders into DQBF,
and the certificate checker.

| Dir | In | Out | Purpose |
|---|---|---|---|
| `eqfob/` | `.eqfob` | DQDIMACS + Python AST | Bit-vector modeling language with ∃-quantified functions |
| `verify/` | DQDIMACS + AIGER (or `.frp`) | pass/fail | Independent solution / refutation checker |
| `qbvf2dqbf/` | SMT-LIB2 BV/UFBV | DQDIMACS | Bit-blast quantified BV under its prefix |
| `bmc2dqbf/` | AIGER circuit + black-box annotations + bound `k` | DQDIMACS | Incomplete-design BMC / PEC encoding |
| `ltlsynth2dqbf/` | TLSF / LTL + state bound `n` | DQDIMACS | Bounded reactive synthesis encoding |

## Shared conventions

- Every encoder is a Python package with a pure
  `encode(problem, **opts) -> dqbf.Formula` function plus a thin `cli.py`.
  The pure function is what tests import.
- Every encoder writes a **comment header** into its DQDIMACS output
  recording the source file, encoder version, and options — so a
  `.dqdimacs` found in the wild is traceable.
- Generated existential variable IDs carry a **symbol map** (in the
  comment header) back to source-level names, so `tools/verify/` can
  present certificates in source terms.
