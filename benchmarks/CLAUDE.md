# benchmarks/

```
train/     What the improvement loop iterates on. Many small families.
valid/     Held back from the loop; checked periodically during dev.
test/      Competition / externally curated sets. Milestone eval only.
runner/    Parallel harness, multi-solver compare, interactive HTML report.
_downloads/ (gitignored) tarball cache for download_benchmarks.sh
```

See `../README.md` § "Benchmark split" for the rationale, and
`docs/IMPROVEMENT_LOOP.md` for the loop mechanics.

## Provenance conventions (apply to every generated instance)

1. **Header comment.** The first lines of every `.dqdimacs`/`.qdimacs`
   we generate are `c` comments naming the producing script, the seed /
   parameters, and the source file (e.g. the `.eqfob` or `.aag`).
2. **Commit the source.** For EQFOB-compiled instances, commit the
   `.eqfob` next to the `.dqdimacs.gz`. For BMC, commit the `.aag`.
   For random generators, commit the generator and its manifest with
   per-instance seeds. The compiled file alone is never enough.
3. **One family = one directory** with its own `manifest.json`
   (`[{"path", "expected", "tags", "params"}]`) and a short `README.md`
   stating what the family measures.

## test/ sources

| Set | URL | Format | In repo? |
|---|---|---|---|
| **QBFLIB DQBF** | https://www.qbflib.org/DOWNLOADS/dqdimacs.zip | DQDIMACS | yes → `test/dqbf_qbflib/{bloem,tentrup,balabanov,scholl}/` |
| QBFEVAL'20/'23 PCNF | https://qbf23.pages.sai.jku.at/gallery/ | QDIMACS | script |
| SMT-LIB BV/UFBV/ABV | https://zenodo.org/records/15493090 | SMT-LIB2 | script |
