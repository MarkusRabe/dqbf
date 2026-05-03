# tools/pec2dqbf/ — Partial Equivalence Checking → DQBF

Encode verification of an **incomplete sequential circuit** (one or more
black-box gates) as a DQBF.

This is the Gitina et al. encoding: each black-box output becomes an
existential whose dependency set is exactly the wires feeding that black
box; primary inputs are universal; the matrix is the `k`-step unrolling
of `init ∧ ⋀ trans ∧ goal`. The black-box function is reused at every
time frame via shared dependency sets — that reuse is exactly what DQBF
buys over a SAT unrolling. PEC and DQBF are polynomially equivalent
(both NEXPTIME-complete).

For plain bounded model checking *without* black boxes, see
`tools/bmc2dqbf/` — that question collapses to QBF.

## Layout

```
aiger_seq.py   sequential-AIGER reader (latches; first output = bad)
encode.py      encode_unrolled / encode_succinct / encode dispatch
cli.py         python -m tools.pec2dqbf.cli FILE.aag -k K --blackbox G,G ...
```

## References

- Gitina, Reimer, Sauer, Wimmer, Scholl, Becker. *Equivalence Checking of
  Partial Designs Using Dependency Quantified Boolean Formulas.* ICCD
  2013. https://ieeexplore.ieee.org/document/6657071
- Scholl, Wimmer et al. *Analysis of Incomplete Circuits Using Dependency
  Quantified Boolean Formulas.* 2018.
  https://link.springer.com/chapter/10.1007/978-3-319-67295-3_7
- `docs/references/gitina_2013_pec_dqbf.md`
