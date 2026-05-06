# benchmarks/train/pec_circuits/

Partial Equivalence Checking instances generated from the in-repo
sequential circuits (`tools/bmc2dqbf/circuits.py`) via
`tools/pec2dqbf/encode.py` (Gitina et al. encoding).

| Param | Sweep | What it controls |
|---|---|---|
| circuit | mutex, fifo1, alu_add | the safe sequential design |
| `N` | 4..24 | bit-width / channel-count |
| `K` | 2,4,8 | BMC depth |
| `n_bb` | 1,2,3 | number of black-boxed gates |
| kind | complete, mutant | original vs one bad-cone gate negated |

Black-boxes are picked from *transition-only* gates with the largest
primary-input cones (the bb dependency-set size is what makes PEC hard).
The `expected` field is set by an hqs probe at generate time; without
hqs available it falls back to `"unknown"`.

Hardest instances at the default sweep are `alu_add` `complete` at
N≥16, K=8, where the solver must synthesize the deep ripple-carry
gates from their full operand-input cone.

External PEC sets (Freiburg `bitcell`/`lookahead`/`pec_xor`) are
referenced in the literature (see `tools/pec2dqbf/CLAUDE.md`) but not
publicly archived as `.dqdimacs`; the QBFEVAL DQBF track (in
`benchmarks/holdout/`) contains the `bloem_*` and `scholl_*` families
as test-only.

## Encoding shape

`∀ inputs . ∃ bb_outᵢ(coneᵢ), wires(inputs)`. Each black-box output
bit has `dep =` exactly the primary inputs feeding that gate's cone
— different black-boxes have **different, incomparable** dep-sets, so
this is genuine DQBF whenever `n_bb ≥ 2`. SAT ⇔ some black-box
implementation makes the two designs equivalent (`_complete`: yes,
the original gate; `_mutant`: no, the mutation is observable).

## Compare against

ABC's `cec` on the fully-specified circuits (no black boxes) gives
the propositional baseline. With black boxes present there is no
non-DQBF tool that decides PEC exactly; QBF over-approximates by
giving each black-box dep = all inputs.

## Literature

- Gitina, Reimer, Sauer, Wimmer, Scholl, Becker. *Equivalence
  Checking of Partial Designs Using Dependency Quantified Boolean
  Formulas.* ICCD 2013.
- Scholl, Becker. *Checking Equivalence for Partial Implementations.*
  DAC 2001 — the QBF over-approximation.
- Wimmer et al., *HQSpre* (TACAS'17) — preprocessing that often
  collapses these to QBF.
