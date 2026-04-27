# tools/bmc2dqbf/ — Bounded Model Checking / PEC → DQBF

Encode verification of an **incomplete circuit** (one or more black boxes)
as a DQBF.

## Encoding

Each black-box output bit becomes an existential variable whose dependency
set is exactly that black box's input wires. Primary inputs are universal.
For combinational PEC the matrix is `spec ≡ impl`; for sequential BMC at
bound `k` it is the `k`-step unrolling of `init ∧ ⋀ trans ∧ ¬prop`, with
the **same** black-box function reused at every time frame via shared
dependency sets — this reuse is precisely what DQBF buys over a SAT
unrolling. PEC and DQBF are polynomially equivalent (both
NEXPTIME-complete).

## References

- Gitina, Reimer, Sauer, Wimmer, Scholl, Becker. *Equivalence Checking of
  Partial Designs Using Dependency Quantified Boolean Formulas.* ICCD
  2013. https://ieeexplore.ieee.org/document/6657071
- Scholl, Wimmer et al. *Analysis of Incomplete Circuits Using Dependency
  Quantified Boolean Formulas.* 2018.
  https://link.springer.com/chapter/10.1007/978-3-319-67295-3_7
- Benchmark source: HQS PEC instances (see `../../benchmarks/dqbf/`).

## Plan

- [ ] Input: AIGER 1.9 with a side-file listing black-box latches/gates,
      plus a safety property (bad-state output) and bound `k`.
- [ ] Combinational PEC encoder (k=0).
- [ ] Sequential unrolling with black-box dependency sharing.
- [ ] Reproduce a subset of the Freiburg PEC benchmarks bit-exactly so we
      can diff against the published `.dqdimacs`.
