# benchmarks/

Instances + a parallel runner. The "official" QBF/QBVF/DQBF competition
sets are the regression baseline; the **EQFOB families** under
`eqfob/` are the primary research target.

## Layout

```
qbf/        QDIMACS — QBFEVAL competition sets (download script; not committed)
dqbf/       DQDIMACS — QBFEVAL DQBF track + Freiburg HQS PEC/synthesis sets (committed, small)
qbvf/       SMT-LIB2 BV/UFBV — SMT-LIB release (UFBV/ABV committed; BV via script)
eqfob/      our families — see eqfob/CLAUDE.md
runner/     parallel harness + result tables
_downloads/ (gitignored) tarball cache for the download script
```

## Sources

| Set | URL | Format | Size | In repo? |
|---|---|---|---|---|
| QBFEVAL'23 PCNF | https://qbf23.pages.sai.jku.at/gallery/ | QDIMACS | 160 MB | script |
| QBFEVAL'23 QCIR | same | QCIR | 640 MB | script |
| QBFEVAL'20 PCNF | same | QDIMACS | 368 MB | script |
| **QBFEVAL DQBF track** | same | DQDIMACS | **11 MB** (354 inst.) | **yes** → `dqbf/qbfeval/` |
| Freiburg HQS PEC/synth | see `dqbf/hqs/README.md` (the published `HQS.zip` is solver source, not instances; benchmark archive TBD) | DQDIMACS | — | README only |
| QBFLIB historical | https://www.qbflib.org/index_eval.php | QDIMACS | varies | script |
| SMT-LIB BV (quantified) | https://zenodo.org/records/15493090 | SMT-LIB2 | 102 MB | script |
| SMT-LIB UFBV | same | SMT-LIB2 | ~1 GB unpacked | script — see `qbvf/ufbv/README.md` |
| SMT-LIB ABV | same | SMT-LIB2 | ~29 MB unpacked | script — see `qbvf/abv/README.md` |
| Pedant eval set | https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2022.20 | DQDIMACS | small | reference |
| DQBDD eval set | https://github.com/jurajsic/DQBDD | DQDIMACS | small | reference |

**Licensing.** Competition sets are distributed for research use without a
uniform license; SMT-LIB is per-file CC-BY 4.0. Committed archives keep
their upstream `LICENSE`/`README` alongside. Anything with unclear
redistribution terms stays behind `scripts/download_benchmarks.sh`.

## Conventions

- Instances >1 MB **must** be `.gz`-compressed in the tree.
- Generated EQFOB instances are **not** committed; commit the generator
  and a `manifest.json` listing {params → expected result}.
- Expected results live in the runner manifest (see `runner/CLAUDE.md`),
  not in filenames — but filenames may *also* carry `_sat`/`_unsat`
  suffixes for human readability where upstream already does so.

## Plan

- [ ] `scripts/download_benchmarks.sh` — fetch + checksum the large sets
      into `_downloads/`, unpack into `qbf/` / `qbvf/`.
- [x] Commit QBFEVAL DQBF track with provenance README.
- [ ] Locate the actual HQS PEC/controller-synth instance archive (the
      published `HQS.zip` is the solver, not the benchmarks).
- [ ] `runner/` MVP: parallel exec + per-family summary table.
- [ ] EQFOB generators for each family under `eqfob/`.
