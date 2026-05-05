# tools/progequiv2dqbf

Program-equivalence → DQBF, with memory as a Skolem function
`mem(step, addr)`. See `encode.py` docstring for the prefix shape.

**Status: stub.** `encode_bounded` builds a well-formed DQBF (DQDIMACS
roundtrips, dep-set shape verified). Semantic validation against
`core.semantics.is_true` is **xfail**: the encoder reifies every
guard as a Tseitin existential, so even the W=1/A=0/R=1/K=2 instance
has ~27 existentials and `is_true` (which enumerates the full Skolem
product) is intractable. `encode_coupling` is a declared
`NotImplementedError`.

Next steps (whoever picks this up):
- **Inline guards as clause prefixes** (drop the `T0`/`at`/`halted`/
  `g` Tseitin vars; emit `[-t₀, ...]` directly). Target ≤12
  existentials at the smallest config so `is_true` decides it.
- Validate `_emit_step` against a Python reference interpreter on
  random programs at W=2,A=2,K=4.
- Replace per-instruction frame clauses with a single mem-frame
  axiom guarded by "no STORE fired".
- Fill `product_transition` and reuse
  `tools.hwmc2dqbf_indinv.encode.encode_indinv`.
