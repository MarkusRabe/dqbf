# syntcomp_legacy — SYNTCOMP TLSF v2023 (training subset)

20 small TLSF instances taken from the SYNTCOMP benchmarks repo at tag
`v2023.4`, restricted to basenames that **no longer appear** in the
latest tag (`v2026`) — they were renamed or dropped between editions.

**Source**: <https://github.com/SYNTCOMP/benchmarks> @ `v2023.4`
(families: `tsl_smart_home_jarvis`, `tsl_paper`, `lily`, `ltl2dba`,
`ltl2dpa`, `detector`, `detector_unreal`).

**Held out for `test/`**: SYNTCOMP `v2026`
(`benchmarks/test/syntcomp/download.sh` is pinned to that tag).
Verified zero basename overlap.

**Not yet runnable**: `tools/ltlsynth2dqbf/` is a stub, so neither DQBF
solvers nor synthesis tools are wired for `.tlsf` input. This family
exists so the encoder has known-result instances to develop against.
