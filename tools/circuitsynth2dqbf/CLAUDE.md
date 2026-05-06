# circuitsynth2dqbf

Minimal-circuit synthesis as DQBF: "∃ an SLP of k gates over the full
binary basis B₂ computing function f for all inputs."

- `spec_functions.py` — target-function library + known B₂ optima.
- `encode.py` — `encode_gates(spec, k)` / `encode_depth(spec, d, w)`.
- Feeds `benchmarks/train/circuit_synth_{gates,depth}/`.

Gate operations are encoded by their 4 truth-table bits, so the basis
is all 16 two-input functions. Input selectors are one-hot (pairwise
AMO ≤5, ladder above). The spec circuit is structural for the
reductions/adder/feistel and truth-table otherwise (n_inputs ≤ 10).

References: Kojevnikov–Kulikov–Yaroslavtsev SAT'09; Knuth TAOCP 7.1.2.
