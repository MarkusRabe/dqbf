# benchmarks/train/ — scalable generated families

These are what the prover-improvement loop iterates against. Every
family is a **generator**, not a set of files: difficulty is a dial
(bit-width `N`, BMC bound `k`, …) so the loop can ask "largest `N`
solved within budget?".

Each family directory contains:

- `generate.py` — builds instances via the `tools.eqfob` API; takes the
  scale parameter(s) on the CLI; writes `.dqdimacs.gz` + `manifest.json`
  under a build dir.
- `README.md` — what the family measures and why.

Generated `.dqdimacs` files are **never** committed.

## Families

| Dir | Scale param | What it measures |
|---|---|---|
| `bitwidth_scaling/` | width `N` | per-BV-op difficulty curve: `∃f. ∀x[,y]. f(..) == op(..)` |
| `dep_cycle/` | width `N` | the §6 dependency-cycle counterexample; exercises SFEx specifically |
| `bmc_mutex/` | bound `k` | k-step mutex with one black-box arbiter |
| `synthesis_invertibility/` | width `N` | `∃f. ∀x. op(f(x),x) == c` invertibility conditions |

## Contract with the runner

`generate.py --out DIR -D NAME=V ...` must write `DIR/manifest.json` of
the form `[{"path", "expected", "params": {...}, "tags": [...]}]` and
the referenced `.dqdimacs.gz` files. The runner discovers the family via
`benchmarks/runner/manifest.load_family("train/<name>")`.
