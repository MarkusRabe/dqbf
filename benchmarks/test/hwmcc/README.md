# HWMCC — Hardware Model Checking Competition

Sequential AIGER circuits with safety/liveness properties. Kept in the
**original `.aig`/`.aag` format** so HW model checkers (`abc`, `avy`,
`nuXmv`, …) and our `tools/bmc2dqbf` translator both consume them.

The archives are large (hundreds of MB) — instances are **not
committed**. Run `./download.sh` to fetch into `instances/`
(gitignored).

| Year | URL | Tracks |
|---|---|---|
| HWMCC'20 | https://fmv.jku.at/hwmcc20/ | bit-vector + word-level (Btor2) |
| HWMCC'19 | https://fmv.jku.at/hwmcc19/ | AIGER single-safety |
| HWMCC'17 | https://fmv.jku.at/hwmcc17/ | AIGER deep / single / liveness |

For DQBF comparison: feed `.aag` instances to `dqbf-bench multi` with
`--solvers abc-bmc,...`; the runner translates to DQDIMACS via
`tools/bmc2dqbf` for the DQBF backends.
