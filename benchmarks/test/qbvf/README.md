# test/qbvf — Quantified Bit-Vectors (BLOCKED)

SMT-LIB2 `BV`/`UFBV`/`ABV` benchmarks bit-blasted under their
quantifier prefix to DQBF. UFBV/ABV are the interesting ones: an
uninterpreted function `f : BV[n] → BV[m]` becomes `m` existential
bits each depending on the `n` argument bits — natively DQBF.

## Status: blocked on `tools/qbvf2dqbf` (2026-05-10)

`tools/qbvf2dqbf/encode.py` is a stub (`raise NotImplementedError`).
Per its `CLAUDE.md`, the plan is to bit-blast via the EQFOB lowering
once that is merged. Until then, no QBVF instances can be generated.

## What unblocks this

1. Implement `tools/qbvf2dqbf/encode.py`. The hard part is the
   bit-blaster (BV ops → CNF over per-bit literals); the prefix /
   dependency part is straightforward once that exists.
2. `download.sh` from the per-logic Zenodo files (sha256 pinned):
   - `ABV.tar.zst` (1.2 MB, ≈4 975 instances)
   - `UFBV.tar.zst` (1.7 MB)
   - Filter to instances with a `(set-info :status sat|unsat)` for
     `expected`; instances without status get `unknown`.
3. `generate.py` mirroring `test/hwmcc/generate.py`: pick a small
   subset, encode, write per-logic manifests.

## Sources

| Logic | URL (Zenodo) | Size |
|---|---|---|
| `ABV` | https://zenodo.org/api/records/15493090/files/ABV.tar.zst/content | 1.2 MB |
| `UFBV` | https://zenodo.org/api/records/15493090/files/UFBV.tar.zst/content | 1.7 MB |

License: per-file CC-BY 4.0 (SMT-LIB).
