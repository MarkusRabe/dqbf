# hwmcc_legacy — HWMCC'17 single-safety AIGER (training subset)

25 small (≤2 KB binary) instances drawn from the HWMCC'17 single-safety
track, committed as both `.aig` (binary, native to abc) and `.aag`
(ASCII, what `_find_source_aag()` matches).

**Source**: <http://fmv.jku.at/hwmcc17/hwmcc17-single-benchmarks.tar.xz>
(300 instances; the 25 here are the smallest, spanning the `bob*`,
`eijk*`, `pdt*`, `nusmv*`, `vis*`, `intel*`, `nec*`, `texas*` prefixes).

**Held out for `test/`**: HWMCC'20 (`benchmarks/test/hwmcc/download.sh`).
Verified zero basename overlap between this set and the HWMCC'20
archive contents.

**Running**: HW model checkers (abc-bmc/abc-pdr) consume the `.aag`
directly. DQBF solvers need a bounded encoding — run each `.aag`
through `tools/bmc2dqbf` at a chosen `k`; until then they report
`error` on this family.
