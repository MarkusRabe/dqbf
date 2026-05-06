# circuit_synth_gates

Minimal-gate-count circuit synthesis as DQBF.

## Encoding

For a target function `f : 𝔹ⁿ → 𝔹ᵐ` and a budget `k`, the formula
asserts the existence of a straight-line program of `k` two-input
gates over the full binary basis B₂ (all 16 functions) that computes
`f` on every input. SAT means such a circuit exists; UNSAT is a lower
bound `C(f) > k`.

Prefix shape:

| variable group | quantifier | dependency | role |
|---|---|---|---|
| `x[1..n]` | ∀ | — | inputs |
| `sa,sb,op,so` | ∃ | ∅ | circuit topology (gate inputs, truth table, output wire) |
| `a,b,v,spec` | ∃ | `{x}` | per-input gate values + Tseitin spec |

The dep-∅ existentials encode a fixed circuit; the dep-`{x}`
existentials carry its evaluation. The matrix is

    v_i ↔ op_i[2·a_i + b_i],  a_i ↔ pool[sa_i],  b_i ↔ pool[sb_i],
    spec_o ↔ pool[so_o]   for each output o.

The two incomparable dependency sets make this genuine DQBF rather
than QBF.

## Instances

For each (function, bitwidth `n`) the generator emits three `k`
points: `{opt−1, opt, opt+1}` when the B₂ optimum is known (giving
one UNSAT and two SAT), otherwise `{⌈upper/2⌉, upper, upper+2}` (one
unknown and two SAT). Functions: AND/OR/XOR-reduce, majority,
exactly-k, threshold, equality, less-than, adder, incrementer,
multiplier, popcount, leading-zero-count, mux, priority encoder,
one-hot decoder, one Feistel round, and tiny floating-point add
(E2M3/E3M2). Bitwidths sweep `{2,4,8,16,32,64}` per a per-function
cap.

## References

- Kojevnikov, Kulikov, Yaroslavtsev. *Finding Efficient Circuits Using
  SAT-Solvers.* SAT 2009.
- Knuth. *The Art of Computer Programming*, Vol. 4A, §7.1.2 (Boolean
  evaluation).
- Alur et al. *Syntax-Guided Synthesis.* FMCAD 2013 (the SyGuS line —
  same problem, richer grammars).
