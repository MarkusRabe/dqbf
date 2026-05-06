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

## Directory layout

```
train/<family>/                 one per problem source (no _v2/_v3 suffixes)
  generate.py                   emits all variants
  README.md                     documents every variant
  <variant>/                    one per *encoding* (descriptive, not "v2")
    manifest.json               [{"path", "expected", "params"}]
    *.dqdimacs.gz               (gitignored)
    *.aag / *.eqfob / *.asm     committed source assets
```

- **Top level = problem source.** `bmc_circuits`, `collatz`, `cbmc`,
  `pec_circuits`. Never `<family>_v2` — when a family grows, add a
  variant subdir, don't fork the family.
- **Variant = encoding, not version.** Use names that say *how* the
  problem is encoded: `unrolled`, `succinct`, `inductive`, `flat`,
  `miter`, `mem_trace`, `uf_lifted`. Avoid `v1/v2/v3`. Difficulty
  tiers (easy/hard, width 2/4/8) are *parameters* recorded in the
  filename and manifest, not separate variant dirs.
- **No instances at the family root.** Instances live under
  `<variant>/` (or `<variant>/<sub>/` for circuit-per-subdir
  families). A family with one encoding uses `instances/` as its
  single variant.
- **One generator per family.** `<family>/generate.py` emits *all*
  variants; one `manifest.json` per variant dir. Non-instance assets
  (AIGER sources, `.asm` programs, `.eqfob`) sit next to the
  instances they produce or under `<family>/<variant>/sources/`.

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
