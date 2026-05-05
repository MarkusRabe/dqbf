# Blocked Clause Elimination for DQBF

What `bce.rs` implements and why the dependency restriction matters.

## SAT-BCE (Järvisalo–Biere–Heule, TACAS 2010)

A clause C is **blocked** on literal l ∈ C iff every resolvent of C on
l is a tautology — i.e., for every clause D with ¬l ∈ D there is some
witness p ∈ C\{l} with ¬p ∈ D. Removing all blocked clauses preserves
propositional satisfiability. Reconstruction: if the model M of the
reduced formula has M ⊭ C, flip M[var(l)]; every D with ¬l ∈ D stays
satisfied because ¬p ∈ D was already true (p ∈ C and M ⊭ C ⇒ p false).

## QBF-BCE (Heule–Järvisalo–Biere, LPAR 2015; HQSpre §4.2)

Same syntactic check, but the **blocking literal l must be
existential**. Universal-blocked is unsound: reconstruction can't flip
a universal in the Skolem-function world. The witness p may be
universal or existential.

## DQBF-BCE (`bce.rs`)

QBF-BCE plus a **dependency restriction on each witness**:

> C is DQBF-blocked on existential l iff for every D with ¬l ∈ D
> there exists p ∈ C\{l} with ¬p ∈ D **and dep(var(p)) ⊆ dep(var(l))**.
> For universal p that means var(p) ∈ dep(l).

The check at `bce.rs:102` is `seen[lix(-q)] && dep_subset(qv, pivot)` —
the tautology test and the dep restriction in one comparison.

### Why the restriction is needed

Reconstruction sets `sk[var(l)](α|_dep(l)) := sign(l)` for every
universal point α where M ⊭ C. Under DQBF, points α, α′ that agree on
dep(l) must give l the same value, so the flip applies to *all* of
them. At such an α′, every D with ¬l ∈ D loses its ¬l literal. It must
stay satisfied by ¬p instead. We know p(α)=false (since C(α) was
false). But p(α′)=false is only guaranteed if p is determined by
dep(l) — i.e., dep(p) ⊆ dep(l).

### Worked example (QBF-BCE unsound, DQBF-BCE catches it)

```
∀u₁ u₂. ∃e₁(u₁). ∃e₂(u₂).
  C₁ = {e₁, e₂}
  C₂ = {¬e₁, ¬e₂}
  C₃ = {e₂, u₂}
  C₄ = {¬e₂, ¬u₂}
```

C₃, C₄ force e₂ = ¬u₂. Substituting into C₁, C₂ gives e₁ ↔ u₂. But e₁
depends only on u₁ — at (u₁=0, u₂=0) and (u₁=0, u₂=1) e₁ must take
both values. **UNSAT.**

QBF-BCE on C₁ with l=e₁: the only D with ¬e₁ is C₂; the resolvent
{e₂, ¬e₂} is a tautology (witness p=e₂). So QBF-BCE removes C₁. The
residue {C₂, C₃, C₄} is **SAT** (e₁=false, e₂=¬u₂) — wrong answer.

DQBF-BCE on C₁ with l=e₁: witness p=e₂ has dep(e₂)={u₂} ⊄ dep(e₁)={u₁}.
Not blocked. ✓

### A case where DQBF-BCE is conservative (but harmlessly so)

```
∀u₁ u₂. ∃e₁(u₁). ∃e₂(u₂).  {e₁, e₂}  {¬e₁, ¬e₂}
```

This is **SAT** (e₁=true, e₂=false). SAT/QBF-BCE would remove both
clauses and correctly say SAT. DQBF-BCE refuses (same dep-subset
failure as above) and leaves both clauses. Harmless — expand's
slot-DPLL solves it instantly anyway — but it shows the dep check can
be stricter than necessary on individual instances.

## Tautologies

The blocked test *is* "every resolvent is a tautology", so there's no
separate tautology-handling pass. Tautological **input** clauses are
dropped before BCE (saturate's load loop has
`if is_tautology(c) { continue; }`), so they never reach the BCE queue.

## Reconstruction cost

Reconstruction iterates the removal stack in reverse; for each
(C, l) it checks all 2^|dep(l)| dep-projections of the universal cube.
`dqbf_bce` caps `max_stack ≈ 10M / 2^nu` (where `nu` is the parameter,
not the formula's |U|) so the total stays under ~10M evals. That's why
`solve()` calls BCE twice: `sat_bce` with `nu=0` (no cap — can fully
empty the matrix) for the saturation/CDCL clause set, and `cert_bce`
with `nu = min(|U|, 16)` for the SAT-cert reconstruction stack.

## Fire rate (340-instance train sample, 23 families)

| Metric | Value |
|---|---|
| Removed ≥1 clause | 93% of instances |
| Emptied the matrix (proves SAT alone) | 20% |
| Median removal | ~15-25% of clauses |

Families where it **empties the matrix**: `bitwidth_scaling/*`
(∃f.∀x. f(x)=op(x) is pure Tseitin gate definitions; every clause is
blocked on its defining-aux literal), `bmc_circuits/shift_reg`,
`synthesis_invertibility/{add,add_zero}_n*`.

Families where it **removes 7-50% but never empties**: all `bmc_*`
(gate clauses go; transition relation and property constraints stay).

Families where it **does nothing**: `random_qbf`, `random_bv` (no gate
structure), `dep_cycle` (every potential witness fails the dep-subset
check), `peano_v2_*` partially (XOR is 4 clauses; only some block).

## Incremental BCE

After each saturate slice, when Db has grown by ≥50% + 256 clauses,
`incremental_bce` re-runs BCE on the live clause set and marks
newly-blocked clauses dead. Sound: BCE preserves equisat on any CNF,
and the live set (input ∪ derived) is matrix-valid. The `.frp` steps
already recorded for those clauses stay; they just stop participating
in future resolutions. Net effect on the current train set: 0
(derived clauses on the bottleneck families don't expose new blocked
clauses), but the hook is in place.
