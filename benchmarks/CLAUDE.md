# benchmarks/

```
holdout/   Competition sets (QBFEVAL DQBF, SMT-LIB BV/UFBV, …).
           Evaluation only — NEVER used inside the improvement loop.
train/     Scalable EQFOB-generated families. The loop iterates here.
runner/    Parallel harness, result tables, two-run compare.
_downloads/ (gitignored) tarball cache for download_benchmarks.sh
```

See `docs/IMPROVEMENT_LOOP.md` for why the split exists and the
acceptance gate.

## holdout/ sources

| Set | URL | Format | Size | In repo? |
|---|---|---|---|---|
| **QBFEVAL DQBF track** | https://qbf23.pages.sai.jku.at/gallery/ | DQDIMACS | 11 MB (354) | **yes** → `holdout/dqbf/qbfeval/` |
| QBFEVAL'20/'23 PCNF | same | QDIMACS | 160–368 MB | script |
| Freiburg HQS PEC/synth | see `holdout/dqbf/hqs/README.md` | DQDIMACS | — | README only |
| SMT-LIB BV/UFBV/ABV | https://zenodo.org/records/15493090 | SMT-LIB2 | large | script — see `holdout/qbvf/*/README.md` |
| QBFLIB historical | https://www.qbflib.org/index_eval.php | QDIMACS | varies | script |

Anything with unclear redistribution terms stays behind
`scripts/download_benchmarks.sh`.

## Conventions

- Instances >1 MB are `.gz`-compressed in the tree.
- `train/` instances are never committed; commit the generator + manifest.
- Expected results live in the runner manifest; filenames may also carry
  `_sat`/`_unsat` suffixes for readability.
