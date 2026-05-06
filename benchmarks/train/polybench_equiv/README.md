# `polybench_equiv` — PolyBench/C loop-transformation equivalence as DQBF

Source-vs-transformed equivalence checking for PolyBench/C kernels
(`jacobi-1d`, `atax`, `2mm`, `mvt`, `gesummv`, …) under
loop-unroll / -reverse / -interchange / -tile / -fuse, encoded so
that **arrays are Skolem functions** rather than unrolled bit-vectors.

## Relation to HEC (arXiv 2506.02290)

HEC verifies the same equivalence relation (PolyBench source vs
loop-transformed) but via *equality saturation over e-graphs* with an
MLIR frontend — term rewriting, no SAT/SMT/DQBF backend. This family
is the bit-precise / function-level complement: it can catch the kind
of boundary / overflow bugs HEC reports finding in `mlir-opt`, and it
is independent of the rewrite-rule set.

## Encodings

Both reuse `tools/progequiv2dqbf/encode.py`, which already models
each program's memory trace as a Skolem function `mem(t, addr)`.

### A. Memory-as-function (implemented)

Identical to `prog_equiv/` but the program pair is a PolyBench kernel
in two iteration orders. Each kernel is hand-lowered to the toy ISA
at a TINY size (`N ∈ {2,4}`, far below PolyBench's MINI which is
N≈40), arrays packed into `mem[0..2^A)`. SAT ⇒ equivalent for all
W-bit inputs within `K` steps.

Feasibility (jacobi-1d, N=4, 21-instr programs, K=24):

| W | \|U\| | \|E\| | \|C\| | pedant |
|---:|---:|---:|---:|---|
| 3 | 16 | 656 | 3 908 | SAT (equiv) |
| 8 | 16 | 1 036 | 6 968 | — |

Kernels with O(N³) operations (`2mm`, `3mm`, `gemm`) need ≈100–200
ISA instructions at N=2; sizes extrapolate to 3–10 k vars — feasible.

### B. Uninterpreted-function lifting (design only)

Replace data-level arithmetic with a Skolem function shared between
both programs — the same trick the encoder already uses for `mem`:

    universals    a*, b*       (probe arguments, W bits each)
    existentials  mul_b(a*, b*)       — one shared function
    constraint    at each call site:  ra==a* ∧ rb==b* → rd ↔ mul(a*,b*)

Then `gemm` etc. need no bit-level multiplier. Equivalence holds
**iff** both programs are observationally equal *for all
interpretations of `mul`* — exactly the condition under which
loop-reordering / -tiling is sound. Associativity / commutativity
rewrites are *correctly rejected* (they change call structure).

Encoder change: add a `UF f rd ra rb` ISA op; allocate one
`f(a*,b*)` block; emit the same consistency clause `mem` already
gets. Estimated ≈40 LOC in `encode.py`.

### What blows up

- PolyBench MINI sizes (N≈40) are out of reach for either encoding
  (O(N²)–O(N³) instructions). TINY (`N ∈ {2,4}`) is the working range.
- Floating-point constants (`0.33333` in stencils) — integerized away
  for now; bit-level FP would need encoding B with `fpmul`/`fpadd` as
  the shared UF, which is exactly where it's strongest.
- The toy ISA needs `addr_bits ≤ word_bits` (registers carry
  addresses) and lacks `MUL`/`LT`; encoding A unrolls loops fully.

## Tools to compare against

| tool | approach | input | comparison |
|---|---|---|---|
| **HEC** (2506.02290) | e-graph equality saturation | MLIR | same kernel/transform pairs; HEC at MINI, this family at TINY |
| **LLVM-Alive2** | SMT translation validation | LLVM IR | per-function equiv after `opt -O2`; SMT arrays vs DQBF Skolem mem |
| **ISL / Pluto** | polyhedral dependence analysis | SCoPs | provides ground-truth `expected` (legal transform ⇒ SAT) |
| pedant / hqs / dqbdd | DQBF solvers | this family | the usual `dqbf-bench multi` |

## Literature

- Pouchet, *PolyBench/C 4.2* (the kernel suite).
- Chen et al., *HEC: Equivalence Verification Checking for Code
  Transformation via Equality Saturation*, arXiv 2506.02290, 2025.
- Bondhugula et al., *Pluto*, PLDI '08 — polyhedral legality.
- Lim et al., *Semantic Equivalence Checking of Decompiled Binaries*,
  CMU SEI 2022 — array-theory precedent (already cited in
  `prog_equiv/README.md`).
- Bryant, German, Velev, *Processor verification using efficient
  reductions to SAT*, CAV '99 — the UF-lifting (Ackermann) lineage.
