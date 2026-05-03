# peano

Peano-style recursive definitions of `+` and `×` over `bv[N]`, posed as
DQBF synthesis. Given only `inc(x) = x+1`, the solver must find a
binary function satisfying the recursion:

| problem | constraints | the function it must find |
|---|---|---|
| `add` | `add(a,0)=a`, `add(a,b+1)=add(a,b)+1` | `a+b` |
| `mul` | `mul(a,0)=0`, `mul(a,b+1)=mul(a,b)+a` (with `+` given) | `a·b` |
| `both` | `add` axioms ∧ `mul(a,0)=0` ∧ `mul(a,b+1)=add(mul(a,b),a)` | both |

All three are SAT for every `N` (the standard mod-2^N operations
satisfy the recursions, including the wrap at `b=max`). The certificate
*is* the operation. Hardness scales with `N`: the function table has
`2^{2N}` entries, so the solver has to discover the structured circuit
rather than enumerate.
