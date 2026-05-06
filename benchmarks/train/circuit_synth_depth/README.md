# circuit_synth_depth

Minimal-depth circuit synthesis as DQBF — the depth dual of
[`circuit_synth_gates`](../circuit_synth_gates/README.md).

The encoding arranges `d` layers of `w` gates each; gate `(l,·)` may
read inputs and any gate in a layer `< l`. The width `w` is set to
`max(n_inputs, n_outputs)` so the gate budget is non-binding and
depth is the constraint. SAT means a depth-`d` circuit exists; UNSAT
is a lower bound `D(f) > d`.

For each (function, `n`) the generator emits two `d` points:
`{opt−1, opt}` when the depth optimum is known (one UNSAT, one SAT),
otherwise `{⌈upper/2⌉, upper}`. Same function set and references as
the gate-count family.
