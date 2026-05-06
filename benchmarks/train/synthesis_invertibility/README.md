# synthesis_invertibility

Invertibility conditions: for each BV operator template, ask
`∃f:bv[N]→bv[N]. ∀x. op(f(x), x) == c`. SAT iff `op` admits a
left-inverse-like witness; the answer is determined by the algebra of
`op`, independent of `N≥2`, so `expected` is set by construction.

| template | constraint | expected | witness / obstacle |
|---|---|---|---|
| add_zero | `f(x)+x == 0` | sat | `f = -x` (two's-complement negate) |
| xor_const | `f(x)^x == 1` | sat | `f = x^1` |
| and_x | `f(x)&x == x` | sat | `f = x` |
| or_x | `f(x)\|x == x` | sat | `f = 0` |
| or_zero | `f(x)\|x == 0` | unsat | fails for any `x≠0` |
| and_notx | `f(x)&x == ~x` | unsat | bit i needs `x_i ∧ ¬x_i` |
| and_one | `f(x)&x == 1` | unsat | fails at `x=0` |
| shl_x | `(f(x)<<1) == x` | unsat | fails when `x` bit 0 is 1 |

Swept over `N ∈ {4,8,16}`. The `.eqfob` source is committed alongside
each `.dqdimacs.gz` per the repo's provenance rules.

**Encoding.** EQFOB `fun f : bv[N]→bv[N]`; each output bit has
`dep = {x}`. Single-dep-set ⇒ effectively 2QBF.

**Compare against.** cvc5 / z3 with quantified BV — these instances
are exactly the unit tests for invertibility-condition synthesis in
those solvers. cadet/caqe on the QDIMACS.

**Literature.** Niemetz, Preiner, Reynolds, Barrett, Tinelli —
*Solving Quantified Bit-Vectors Using Invertibility Conditions* (CAV
2018); Preiner, Niemetz, Biere — *Counterexample-Guided Model
Synthesis* (TACAS'17).
