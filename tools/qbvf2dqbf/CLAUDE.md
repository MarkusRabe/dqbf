# tools/qbvf2dqbf/ — Quantified Bit-Vectors → DQBF

Bit-blast an SMT-LIB2 `BV`/`UFBV` formula under its quantifier prefix.

## Why this is (mostly) QBF

A QBVF with a **linear** prefix bit-blasts to ordinary QBF — the
dependency sets are nested by construction. DQBF only adds power when the
source has uninterpreted function symbols (`UFBV`) or the prefix is
already non-linear. So this tool's value is:

1. a uniform front-end so the prover/benchmark runner can ingest SMT-LIB;
2. the `UFBV` case, where each uninterpreted `f : bvN → bvM` becomes `M`
   existentials each depending on the `N` argument bits — a genuine DQBF.

## References

- Wintersteiger, Hamadi, de Moura. *Efficiently Solving Quantified
  Bit-Vector Formulas.* FMCAD 2010 / FMSD 2013.
  http://leodemoura.github.io/files/ufbv_journal.pdf
- Kovásznai, Fröhlich, Biere. *More on the Complexity of QF_BV with
  Binary-Encoded Bit-Width* (and `bv2epr`).
  https://link.springer.com/chapter/10.1007/978-3-642-38536-0_33
- SMT-LIB BV/UFBV theory: https://smt-lib.org/theories.shtml

## Plan

- [ ] PySMT-based SMT-LIB2 parser → internal BV AST shared with
      `tools/eqfob/ast.py` (reuse the bit-blaster).
- [ ] Linear-prefix path: emit QDIMACS (a DQDIMACS subset).
- [ ] `UFBV` path: Ackermannize or dependency-encode UF symbols → DQDIMACS.
- [ ] Golden tests against `benchmarks/qbvf/` (SMT-LIB UFBV/ABV sets).
