# DQDIMACS

DQDIMACS extends [QDIMACS](https://www.qbflib.org/qdimacs.html) with one
extra prefix-line form for explicit dependency sets. There is no
standalone formal spec; the format is defined by convention across iDQ,
HQS, dCAQE, DQBDD and Pedant.

## Grammar

```
file    := header prefix clause*
header  := "p cnf" VARS CLAUSES "\n"
prefix  := (aline | eline | dline)*
aline   := "a" VAR+ "0\n"                  -- universal block
eline   := "e" VAR+ "0\n"                  -- existential; depends on ALL preceding universals
dline   := "d" VAR DEP* "0\n"              -- existential VAR with EXPLICIT dependency set {DEP*}
clause  := LIT+ "0\n"
```

- A `d`-line declares **one** existential and lists its universal
  dependencies (each must have appeared in an earlier `a`-line).
- An `e`-line is shorthand for a `d`-line whose dependency set is every
  universal introduced so far (QDIMACS-compatible).
- Variable IDs are positive integers; literal `-v` is negation.

## Example

```
c  ∀x1 x2. ∃y3(x1). ∃y4(x2). (y3 ∨ y4) ∧ (¬y3 ∨ ¬y4) ∧ (x1 ∨ ¬y3) ∧ (x2 ∨ ¬y4)
p cnf 4 4
a 1 2 0
d 3 1 0
d 4 2 0
3 4 0
-3 -4 0
1 -3 0
2 -4 0
```

## References

- iDQ: https://fmv.jku.at/idq/
- DQBDD: https://github.com/jurajsic/DQBDD
- Pedant: https://github.com/fslivovsky/pedant-solver
- QDIMACS 1.1: https://www.qbflib.org/qdimacs.html
