# EQFOB — Existentially Quantified Functions Over Bit-vectors

EQFOB is a small modeling language for writing **DQBF** problems at the
bit-vector level. An EQFOB file declares parametric bit-widths,
existentially quantifies a set of *functions* over bit-vectors, then
states constraints over BV expressions and applications of those
functions. The compiler bit-blasts to DQDIMACS: each function-output bit
becomes a DQBF existential whose dependency set is exactly the universal
bits reachable from the call's arguments. The point is that DQBF *is*
the logic of "do these Boolean functions exist?" — EQFOB lets you write
that directly instead of hand-encoding clauses.

## File structure

A `.eqfob` file is a sequence of declarations followed by constraints,
in this order:

```
-- comments start with --
param N = 4                  -- 1. width constants (overridable on the CLI)
sort Word = bv[N]            -- 2. named sorts (sugar for bv[...])
fun f : Word, Word -> bv[1]  -- 3. existentially-quantified functions
exists z : Word              -- 4. existential BVs (depend on preceding universals)
forall x : Word              -- 5. universal BVs
f(x, z) == 1                 -- 6. constraints — one per line, implicitly conjoined
```

A `param` is just an integer constant; every `bv[...]` width must be a
literal or a param/sort name, so an instance can be re-generated at a
different scale with `eqfob compile FILE -D N=8`.

Declaration order matters for `exists`/`forall`: an `exists` declared
**before** any `forall` is a Skolem constant (depends on nothing); one
declared **after** some `forall`s depends on all preceding universals,
QBF-style.

## Expression syntax

| Category | Operators | Notes |
|---|---|---|
| Bit-vector arithmetic | `+ - *` and unary `-` | wrapping, two's-complement |
| Bitwise | `& \| ^ ~` | width-preserving |
| Shifts | `<<` `>>` `>>>` | `>>` is **arithmetic**, `>>>` is logical |
| Comparison | `== != < <= > >=` | unsigned; result is `bv[1]` |
| Boolean | `&& \|\| ! -> <->` | operands must be `bv[1]` |
| Slicing | `extract[hi:lo](e)` | inclusive, LSB is bit 0 |
| Extension | `zext[k](e)` `sext[k](e)` | adds `k` high bits |
| Conditional | `ite(c, t, e)` | `c : bv[1]`; `t`, `e` same width |
| Function call | `f(e1, …, ek)` | arity- and width-checked |
| Literals | decimal integers | width inferred from context |

Precedence (high → low): unary, `*`, `+ -`, shifts, `&`, `^`, `|`,
comparisons, `&&`, `||`, `->`, `<->`. Parenthesize when in doubt.

### Conditionals — worked example

```
-- ∃max. ∀x,y. max(x,y) = if x≥y then x else y      (SAT: max is the function)
param N = 2
fun max : bv[N], bv[N] -> bv[N]
forall x : bv[N]
forall y : bv[N]
max(x, y) == ite(x >= y, x, y)
```

`ite` is a BV-level mux: the condition is `bv[1]`, the two branches must
have the same width, and the result has that width. There is no
statement-level `if`; conditionals are expressions only.

### Slicing and extension

```
-- Low bit of x equals (x & 1) restricted to bv[1].   (Tautology)
forall x : bv[2]
extract[0:0](x) == extract[0:0](x & 1)
```

`extract[hi:lo](e)` yields width `hi − lo + 1`. `zext[k](e)` /
`sext[k](e)` add `k` bits (zero / sign-replicated) at the MSB end.

## Core restrictions

EQFOB is deliberately small. The following are **not** supported:

- **No recursion or higher-order.** `fun` declares uninterpreted,
  first-order functions `bvᵐ → bvⁿ`. Functions cannot call functions and
  are not values.
- **Widths are static.** Every width is a compile-time integer; there is
  no dependent typing. Integer literals get their width from context and
  must be unambiguous.
- **Shift amounts are constants.** `e << k` requires `k` to be a literal
  or param; variable shift amounts raise `NotImplementedError`.
- **No `udiv` / `urem`.** Not implemented in the bit-blaster.
- **Signed comparisons** (`slt`, `sle`, …) exist in the AST but have no
  textual syntax yet — `<`, `<=`, `>`, `>=` are always unsigned.
- **One constraint per line.** Each top-level expression must have width
  1 (Boolean); the matrix is the conjunction of all constraint lines.
- **`exists`/`forall` are not nested in expressions.** The quantifier
  prefix is the declaration sequence; the body is quantifier-free.

## Function semantics (Ackermann congruence)

Two textual call sites `f(a)` and `f(b)` introduce **separate**
existential output bits, but the compiler adds a congruence constraint
`a == b → f(a) == f(b)` for every pair of call sites. Consequently

```
fun f : bv[1] -> bv[1]
forall x : bv[1]
f(x) != f(x)
```

is **UNSAT**: the two `f(x)` occurrences must agree, so the inequality
fails. Without congruence the bit-blasted formula would be spuriously
satisfiable.

## Examples

The `.eqfob` files under [`examples/`](examples/) are golden inputs used
by the test suite; each begins with a comment giving the high-level
spec and the expected SAT/UNSAT result.

| File | What it asserts | Result |
|---|---|---|
| `ite_max.eqfob` | `max` realizes `ite(x≥y, x, y)` | SAT |
| `ackermann_neq.eqfob` | `f(x) ≠ f(x)` (congruence forces equality) | UNSAT |
| `extract_low.eqfob` | a function picks out the low bit | SAT |
| `zext_bound.eqfob` | `zext[1](x) < 2` for every 1-bit `x` | SAT (tautology) |
| `add_gt.eqfob` | `∃f,g,z. ∀x. f(x)+z > g(x)` | SAT |
| `dep_cycle.eqfob` | the journal §6 dependency-cycle counterexample | UNSAT |

## Compiling

```bash
eqfob compile examples/ite_max.eqfob -D N=4 -o ite_max.dqdimacs
```

Emits DQDIMACS with a comment header recording the source file and
overrides. The output is consumable by any DQBF solver in this repo and
by `tools/verify/`.
