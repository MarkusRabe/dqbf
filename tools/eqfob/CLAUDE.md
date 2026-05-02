# tools/eqfob/ — the EQFOB language

**EQFOB** ("Existentially Quantified Functions Over Bit-vectors") is a
small modeling language and Python library for writing DQBF problems at
the bit-vector level. An EQFOB file declares parametric bit-widths,
existentially quantifies a set of **functions** over bit-vectors, then
states constraints over BV expressions and function applications. The
compiler bit-blasts to DQDIMACS, mapping each function-output bit to an
existential variable whose dependency set is the bit-blasted argument
bits.

EQFOB exists because DQBF *is* the logic of "do these Boolean functions
exist" — writing that directly at the bit level is painful, and SMT-LIB
UFBV doesn't expose Henkin-style dependency restrictions.

## Language sketch

```
-- widths.eqfob
param A = 8
param B = 8

sort Addr = bv[A]
sort Data = bv[B]

-- existentially quantified functions (the things we synthesize)
fun f : Addr -> Data
fun g : Addr -> Data

-- existentially quantified bit-vectors (ordinary Skolem constants)
exists z : Data

-- universally quantified bit-vectors
forall x : Addr

-- constraints: one per line, implicitly conjoined
f(x) + z > g(x)
f(0) == 0
```

### File structure (in order)

1. `param NAME = INT` — width constants. Every `bv[...]` width is a
   constant expression over these, so an instance can be re-generated at a
   different scale by overriding params on the CLI.
2. `sort NAME = bv[EXPR]` — named widths (sugar).
3. `fun NAME : T1, T2, ... -> Tr` — existentially quantified functions.
   Each takes any number of BV arguments and returns one BV. After
   bit-blasting, each output bit becomes a DQBF existential whose
   dependency set is exactly the bits of the declared argument sorts.
4. `exists NAME : T` — existential BV (depends on **nothing** unless
   declared after a `forall`, in which case it depends on all preceding
   universals — QBF-style).
5. `forall NAME : T` — universal BV.
6. Constraint lines: one Boolean-typed BV expression per line; the matrix
   is their conjunction.

### Expression grammar

Bit-vector: `+ - * udiv urem & | ^ ~ << >> >>> concat extract[hi:lo]
zext[n] sext[n] ite(c,a,b)` and integer literals.
Boolean: `== != < <= > >=` (both `u`/`s` variants), `&& || ! -> <->`.
Function application: `f(e1, ..., ek)` with arity/width checking.

## Python library

`eqfob/` is also importable: build/inspect/transform formulas
programmatically.

```python
from tools.eqfob.eqfob.builder import Problem

p = Problem()
f = p.fun("f", ["bv[8]"], "bv[8]")
x = p.forall("x", "bv[8]")
p.add(f(x) + 1 != f(x))
formula = p.to_dqbf()      # core.Formula
```

The AST is the single source of truth; the `.eqfob` parser builds it, the
DQDIMACS backend consumes it, and the benchmark generators in
`benchmarks/train/*/generate.py` construct it directly.

## Module layout

```
eqfob/
  ast.py        Param, Sort, Fun, Var, Expr nodes
  parse.py      lark grammar → ast
  typecheck.py  width/arity inference and checking
  bitblast.py   Expr → Tseitin CNF; assembles prefix + matrix → core.Formula
  builder.py    the programmatic API above
  cli.py        `eqfob compile FILE.eqfob -o FILE.dqdimacs -D A=16`
examples/       small .eqfob files used as golden tests
```

## References

- DQDIMACS target format: `../../docs/references/dqdimacs.md`.
- py-aiger-bv for the BV→AIG layer:
  https://github.com/mvcisback/py-aiger-bv
- Closest prior language: SMT-LIB `UFBV` (uninterpreted functions over
  BV) — EQFOB differs in making the dependency restriction explicit and
  first-class.
- Width-as-parameter idea: Kovásznai–Fröhlich–Biere, *On the Complexity
  of Fixed-Size Bit-Vector Logics with Binary Encoded Bit-Width*.

## Plan

- [x] Concrete grammar + AST + round-trip tests on `examples/*.eqfob`.
- [x] Type checker with width-mismatch errors.
- [x] Programmatic builder API.
- [x] Bit-blast → CNF; symbol map in DQDIMACS comments.
- [x] CLI with `-D NAME=INT` param overrides.
- [x] `examples/`: `add_gt.eqfob`, `dep_cycle.eqfob`.
- [ ] Missing ops: `udiv`/`urem`, signed comparisons, variable shift.
- [ ] Tighten mypy (currently overridden in `pyproject.toml`).
