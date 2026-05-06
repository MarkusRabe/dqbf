# benchmarks/train/ — scalable generated families

These are what the prover-improvement loop iterates against. Difficulty
is a dial (bit-width `N`, BMC bound `k`, …) so the loop can ask "largest
`N` solved within budget?".

## Layout

```
<family>/
  generate.py        emits all variants
  README.md          documents every variant
  <variant>/         one per *encoding* (descriptive, not "v2")
    manifest.json
    *.dqdimacs.gz    (gitignored)
    *.aag/.eqfob/... committed source assets
```

See `../CLAUDE.md` § Directory layout for the full convention. In
short: **no `_v2`/`_v3` suffixes** — variants describe the *encoding*
(`unrolled`, `succinct`, `inductive`, `flat`, `miter`, `mem_trace`),
and difficulty tiers are parameters in the filename/manifest, not
separate directories.

Generated `.dqdimacs.gz` and `manifest.json` are gitignored. Committed
assets sit alongside them: `.aag` circuit sources, `.eqfob` sources,
`.asm` programs. Exceptions: `random_qbf/` and `random_bv/` commit
their instances as a fixed static reference set.

## Families

Single-variant families use `instances/` as the one variant.

| Family | Variants | Scale | Measures |
|---|---|---|---|
| `bitwidth_scaling/` | `build/` | N | per-BV-op `∃f. ∀x. f(..)==op(..)` difficulty |
| `bmc_circuits/` | `unrolled/`, `succinct/`, `inductive/` | N, k | sequential-circuit BMC under three encodings |
| `bmc_mutex/` | `instances/` | k | k-step mutex with black-box arbiter |
| `cbmc/` | `handwritten/`, `flat/`, `succinct/`, `inductive/` | N, k | C-program BMC |
| `circuit_synth/` | `gates/`, `depth/` | n, k | minimal-circuit search; UNSAT = lower bound |
| `collatz/` | `unrolled/`, `succinct/`, `tonly/`, `inductive/` | N, k, step | modular Collatz reachability |
| `conjunction/` | `instances/` | seed | conjoined random sub-DQBFs |
| `dep_cycle/` | `instances/` | N | the §6 dependency-cycle; exercises SFEx |
| `hwmcc_legacy/` | `instances/` | — | HWMCC AIGER → bounded BMC |
| `hwmc_indinv/` | `inductive/` | N | HWMCC AIGER → inductive-invariant search |
| `peano/` | `instances/` | N | Peano-arithmetic identities via EQFOB |
| `pec_circuits/` | `miter/` | N, k, bb | partial-equivalence checking with black-box gates |
| `pec_counter/` | `instances/` | N | scaling PEC counter family |
| `polybench_equiv/` | `mem_trace/` | W, k | PolyBench-style program equivalence; mem as Skolem fn |
| `prog_equiv/` | `mem_trace/` | W, A, K | toy-ISA program equivalence |
| `random_bv/` | `mixed/`, `over/`, `under/` | width, seed | random EQFOB; constraint-density tiers |
| `random_qbf/` | `2qbf/`, `3qbf/` | seed, size | Chen-Interian random QBF |
| `syntcomp_legacy/` | `instances/` | — | SYNTCOMP TLSF → bounded synthesis |
| `synthesis_invertibility/` | `instances/` | N | `∃f. ∀x. op(f(x),x)==c` invertibility |

## Contract with the runner

`generate.py` writes one `manifest.json` per variant directory of the
form `[{"path", "expected", "params": {...}, "tags": [...]}]`.
`benchmarks.runner.multi.discover()` walks `train/**/manifest.json`.
