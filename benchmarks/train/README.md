# benchmarks/train/ — index

The improvement loop iterates on these families. Each directory has its
own README covering: what problem is encoded, the DQBF prefix shape,
what SAT/UNSAT mean, alternative encodings, native tools to compare
against, and literature pointers. See `../CLAUDE.md` for provenance
conventions and the train/valid/test split.

| family | # | problem | DQBF? | compare against |
|---|---:|---|---|---|
| [`bitwidth_scaling/`](bitwidth_scaling/README.md) | 28 | synthesise one BV op (`∃f∀x. f(x)==op(x)`); scales `\|dep\|` only | 2QBF | caqe / SMT-BV |
| [`bmc_circuits/`](bmc_circuits/README.md) | 1330 | BMC of 27 sequential circuits at width×bound; `unrolled/`, `succinct/`, `inductive/` | succinct/inductive | ABC `bmc3`/`pdr`, nuXmv |
| [`bmc_mutex/`](bmc_mutex/README.md) | — | superseded by `bmc_circuits/unrolled/mutex/` | — | — |
| [`cbmc/`](cbmc/README.md) | ~517 | C-program BMC; `handwritten/`, `flat/`, `succinct/`, `inductive/` | succinct/inductive | CBMC, ESBMC |
| [`circuit_synth/`](circuit_synth/README.md) | 306 | ∃ circuit with ≤k gates / ≤d depth computing f; `gates/`, `depth/` | yes (∅ vs {x}) | ABC `exact`, SyGuS |
| [`collatz/`](collatz/README.md) | 171 | bounded modular Collatz; `unrolled/`, `succinct/`, `tonly/`, `inductive/` × 3 step variants | succinct/tonly/inductive | (none; cadet on unrolled) |
| [`conjunction/`](conjunction/README.md) | 50 | disjoint conjunction of K instances; tests decomposition | inherits | HQSpre |
| [`dep_cycle/`](dep_cycle/README.md) | 4 | journal-§6 dependency cycle; SFEx required | yes | (DQBF only) |
| [`hwmc_indinv/`](hwmc_indinv/README.md) | 45 | ∃ inductive invariant (SAT ⇔ property holds) | yes | ABC `pdr`, rIC3 |
| [`hwmcc_legacy/`](hwmcc_legacy/README.md) | 100 | HWMCC'17 single-safety subset (encoded BMC) | unrolled | ABC, nuXmv |
| [`peano/`](peano/README.md) | 66 | synthesise +/× from Peano recursions | yes | SyGuS, SMT-UFBV |
| [`pec_circuits/`](pec_circuits/README.md) | 324 | partial equivalence checking with black-box gates | yes | ABC `cec` (no-bb baseline) |
| [`pec_counter/`](pec_counter/README.md) | — | single-circuit PEC (3-bit counter) at varied k | yes | — |
| [`polybench_equiv/`](polybench_equiv/README.md) | 24 | PolyBench-style program equivalence; `mem_trace/` | yes | HEC (e-graphs), SMT-array |
| [`prog_equiv/`](prog_equiv/README.md) | 24 | toy-ISA program equivalence; `mem_trace/` | yes | Rêve / SMT-array |
| [`random_bv/`](random_bv/README.md) | 135 | seeded random EQFOB; `mixed/`, `over/`, `under/` | usually | SMT-UFBV |
| [`random_qbf/`](random_qbf/README.md) | 360 | Chen–Interian random; `2qbf/`, `3qbf/` | no (QBF) | cadet, caqe, depqbf |
| [`syntcomp_legacy/`](syntcomp_legacy/README.md) | 15 | SYNTCOMP'23 TLSF subset (encoder is a stub) | — | strix, ltlsynt |
| [`synthesis_invertibility/`](synthesis_invertibility/README.md) | 48 | `∃f∀x. op(f(x),x)==c`; CAV'18 invertibility conditions | 2QBF | cvc5, z3 |

**"DQBF?"** = whether the family has ≥2 incomparable dependency sets.
Families marked "2QBF" or "no" are decidable by QBF/SAT solvers and
serve as cross-check anchors.
