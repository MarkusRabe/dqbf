# benchmarks/

```
test/      Competition sets (QBFLIB DQBF, SMT-LIB BV/UFBV, …).
           Evaluation only — NEVER used inside the improvement loop.
train/     Scalable generated families. The loop iterates here.
runner/    Parallel harness, multi-solver compare, HTML report.
_downloads/ (gitignored) tarball cache for download_benchmarks.sh
```

See `docs/IMPROVEMENT_LOOP.md` for why the split exists and the
acceptance gate.

## test/ sources

| Set | URL | Format | Size | In repo? |
|---|---|---|---|---|
| **QBFLIB DQBF** | https://www.qbflib.org/DOWNLOADS/dqdimacs.zip | DQDIMACS | 7.6 MB (478) | **yes** → `test/dqbf_qbflib/{bloem,tentrup,balabanov,scholl}/` |
| QBFEVAL'20/'23 PCNF | https://qbf23.pages.sai.jku.at/gallery/ | QDIMACS | 160–368 MB | script |
| SMT-LIB BV/UFBV/ABV | https://zenodo.org/records/15493090 | SMT-LIB2 | large | script — see `test/qbvf/*/README.md` |
| QBFLIB historical QBF | https://www.qbflib.org/index_eval.php | QDIMACS | varies | script |

Anything with unclear redistribution terms stays behind
`scripts/download_benchmarks.sh`.

## Conventions

- Instances >1 MB are `.gz`-compressed in the tree.
- `train/` instances are never committed; commit the generator + manifest.
- Expected results live in the runner manifest; filenames may also carry
  `_sat`/`_unsat` suffixes for readability.
