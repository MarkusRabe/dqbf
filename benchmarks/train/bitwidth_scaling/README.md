# bitwidth_scaling — synthesise one BV operator, swept over width

**Problem.** For a fixed bit-vector operator `op` (id, not, inc, add,
and, or, xor), find a function `f` such that `∀x[,y]. f(x[,y]) ==
op(x[,y])` over `bv[N]`. Every instance is **SAT by construction**
(`f := op`); the certificate is the operator's circuit.

**Encoding (EQFOB → DQBF).** Prefix `∃ f-bits(x[,y]) . ∀ x[,y]`:
each bit of `f`'s output is an existential whose dependency set is the
full input vector (`|dep| = N` or `2N`). The matrix is the bit-blasted
equality `f == op`. This is ∀∃ shape (single dep-set), so QBF ⊂ DQBF.

**What it measures.** Isolated scaling of `|dep|` while the matrix
structure stays trivial — a SAT-only difficulty curve. Solvers that
build truth-table Skolem certificates blow up at `2^{2N}` entries for
the binary operators; solvers that emit circuit-shaped certs should
solve every width cheaply.

**Alternatives.** The same operators appear inside `peano/` (with
recursive specs instead of explicit RHS) and as gate definitions
inside `circuit_synth/gates/` (with a gate-count budget instead of
unbounded `f`).

**Compare against.** Any QBF solver (caqe, depqbf, cadet) on the same
QDIMACS; SMT-BV solvers (cvc5, z3) on the original `∃f∀x` formula via
`tools/qbvf2dqbf` in reverse.

**Subdirectories.** `v1/v3/v4/` are width-list wrappers around the
same generator (`v3 ⊂ v1`); PR #2 collapses them to one `build/`.

**Literature.** Kovásznai–Fröhlich–Biere, *On the complexity of
fixed-size bit-vector logics* (CSL'12) — bit-blasting cost; Niemetz et
al. *Solving Quantified Bit-Vectors Using Invertibility Conditions*
(CAV'18).
