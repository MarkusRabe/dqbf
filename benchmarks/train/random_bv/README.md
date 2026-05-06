# random_bv — random EQFOB (∃ functions over bit-vectors)

**Problem.** Seeded random EQFOB programs: declare `n_funs` unary
`bv[W]→bv[W]` functions, then assert `n_constraints` random
(in)equalities between depth-≤2 bit-vector expressions over the
functions and `n_forall` universal vectors. SAT iff some assignment of
truth tables to the functions satisfies every constraint
simultaneously for all inputs.

**Encoding.** EQFOB → DQBF. Each function bit becomes an existential
with `dep =` the bits of its argument; multiple functions over the
same universal share that dep-set, but functions over different
universals get incomparable deps (genuine DQBF when `n_forall ≥ 2`).
Constraint count is the difficulty knob: `under` (1–2, mostly SAT),
`over` (5–7, mostly UNSAT), `mixed` (3–4). The `.eqfob` source is
committed alongside each instance per provenance rules.

**Alternatives.** The same syntactic class is what `tools/qbvf2dqbf`
targets from SMT-LIB UFBV. `synthesis_invertibility/` is the
hand-picked, expected-known subset of this space.

**Compare against.** SMT solvers with quantified BV (`cvc5 --lang
smt2`, z3) on the EQFOB-as-SMT2 rendering; DQBF solvers on the
compiled `.dqdimacs`.

**Literature.** Fröhlich–Kovásznai–Biere, *iDQ: Instantiation-based
DQBF Solving* (POS'14) — random DQBF as a stress test;
Ge–de Moura, *Complete Instantiation for Quantified SMT* (CAV'09).
