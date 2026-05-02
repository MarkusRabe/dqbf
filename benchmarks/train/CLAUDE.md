# benchmarks/train/ — scalable generated families

These are what the prover-improvement loop iterates against. Difficulty
is a dial (bit-width `N`, BMC bound `k`, …) so the loop can ask "largest
`N` solved within budget?".

Each family directory contains a `generate.py` that takes the scale
parameter(s) on the CLI and writes `.dqdimacs[.gz]` + `manifest.json`.
EQFOB-authored families use the `tools.eqfob` API; `random_qbf/`
emits QDIMACS directly.

Generated `.dqdimacs` files are **not** committed — except
`random_qbf/instances/`, which is a fixed 100-instance static set
(QDIMACS, labelled by `random_qbf/label.py` via caqe) used as a
cross-solver correctness reference.

## Families

| Dir | Scale param | Status | What it measures |
|---|---|---|---|
| `bitwidth_scaling/` | width `N` | generator | per-BV-op difficulty curve: `∃f. ∀x[,y]. f(..) == op(..)` |
| `random_qbf/` | seed/size | generator + 100 committed | random 2QBF/3QBF; cross-check against cadet/caqe/rareqs |
| `dep_cycle/` | width `N` | TODO | the §6 dependency-cycle counterexample; exercises SFEx |
| `bmc_mutex/` | bound `k` | TODO | k-step mutex with one black-box arbiter |
| `synthesis_invertibility/` | width `N` | TODO | `∃f. ∀x. op(f(x),x) == c` invertibility conditions |

## Contract with the runner

`generate.py --out DIR -D NAME=V ...` must write `DIR/manifest.json` of
the form `[{"path", "expected", "params": {...}, "tags": [...]}]` and
the referenced instance files. The runner discovers the family via
`benchmarks/runner/manifest.load_family("train/<name>/<out-dir>")`.
