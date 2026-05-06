# benchmarks/train/ — index

The improvement loop iterates on these families. Each directory has its
own README covering: what problem is encoded, the DQBF prefix shape,
what SAT/UNSAT mean, alternative encodings, native tools to compare
against, and literature pointers. See `../CLAUDE.md` for provenance
conventions and the train/valid/test split.

| family | # | problem | DQBF? | compare against |
|---|---:|---|---|---|
| [`bitwidth_scaling/`](bitwidth_scaling/README.md) | 28 | synthesise one BV op (`∃f∀x. f(x)==op(x)`); scales `\|dep\|` only | 2QBF | caqe / SMT-BV |
| [`bmc_circuits/`](bmc_circuits/README.md) | 1064 | BMC of 27 sequential circuits at width×bound, unrolled + succinct | succinct: yes | ABC `bmc3`/`pdr`, nuXmv |
| [`bmc_mutex/`](bmc_mutex/README.md) | — | superseded by `bmc_circuits/mutex/` | — | — |
| [`cbmc/`](cbmc/README.md) | 13 | C BMC via `cbmc --dimacs` (all-∃) | no | CBMC |
| [`cbmc_v2/`](cbmc_v2/README.md) | 400 | 12 ok/bug C algorithms, flat + succinct | succinct: yes | CBMC, ESBMC |
| [`circuit_synth_gates/`](circuit_synth_gates/README.md) | 189 | ∃ circuit with ≤k gates computing f | yes (∅ vs {x}) | ABC `exact`, SyGuS |
| [`circuit_synth_depth/`](circuit_synth_depth/README.md) | 112 | depth-d dual of the above | yes | ABC `exact`, SyGuS |
| [`collatz/`](collatz/README.md) (+[`v2/`](collatz/v2/README.md)) | 169 | bounded modular Collatz reachability, 4 encodings × 3 step variants | succinct: yes | (none; cadet on unrolled) |
| [`conjunction/`](conjunction/README.md) | 50 | disjoint conjunction of K instances; tests decomposition | inherits | HQSpre |
| [`dep_cycle/`](dep_cycle/README.md) | 4 | journal-§6 dependency cycle; SFEx required | yes | (DQBF only) |
| [`hwmc_indinv/`](hwmc_indinv/README.md) | 45 | ∃ inductive invariant (SAT ⇔ property holds) | yes | ABC `pdr`, rIC3 |
| [`hwmcc_legacy/`](hwmcc_legacy/README.md) | 100 | HWMCC'17 single-safety subset (encoded BMC) | unrolled | ABC, nuXmv |
| [`peano/`](peano/README.md) | 66 | synthesise +/× from Peano recursions | yes | SyGuS, SMT-UFBV |
| [`pec_circuits/`](pec_circuits/README.md) | 324 | partial equivalence checking with black-box gates | yes | ABC `cec` (no-bb baseline) |
| [`pec_counter/`](pec_counter/README.md) | — | single-circuit PEC (3-bit counter) at varied k | yes | — |
| [`prog_equiv/`](prog_equiv/README.md) | 24 | program equivalence with `mem(t,a)` as Skolem fn | yes | Rêve / SMT-array |
| [`random_bv/`](random_bv/README.md) | 120 | seeded random EQFOB constraints | usually | SMT-UFBV |
| [`random_qbf/`](random_qbf/README.md) | 360 | Chen–Interian random 2QBF/3QBF | no (QBF) | cadet, caqe, depqbf |
| [`syntcomp_legacy/`](syntcomp_legacy/README.md) | 15 | SYNTCOMP'23 TLSF subset (encoder is a stub) | — | strix, ltlsynt |
| [`synthesis_invertibility/`](synthesis_invertibility/README.md) | 48 | `∃f∀x. op(f(x),x)==c`; CAV'18 invertibility conditions | 2QBF | cvc5, z3 |

`bitwidth_scaling_v3/` is a dead width-list wrapper (no generator
content); PR #2 removes it.

**"DQBF?"** = whether the family has ≥2 incomparable dependency sets.
Families marked "2QBF" or "no" are decidable by QBF/SAT solvers and
serve as cross-check anchors.
