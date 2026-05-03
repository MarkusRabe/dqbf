# bmc_circuits_succinct

Same circuit library as `../bmc_circuits/` (counter, gray, mutex,
shift_reg, fifo1, alu_add), encoded via the **succinct universal
step-counter** scheme: the step index `t` is a `⌈log₂(k+1)⌉`-bit
universal, each input/latch/gate is a single existential function of
`t`, and the transition relation is asserted once over `(t, t+1)`.

The point: instance size grows with `log k` instead of `k`, so deep
bounds stay small. The result is genuine DQBF (the two index copies
have incomparable dependency sets) — solvers that exploit dependency
structure should see the per-step latch functions directly, whereas
solvers that flatten to QBF will suffer the index blowup.

Semantics: ∃-input-trace reachability — equisatisfiable with
`bmc_circuits/` (`safe=False`). See
`tools/bmc2dqbf/encode.py::encode_succinct` for the construction and
`tools/bmc2dqbf/encode_test.py::test_succinct_equisat_with_unrolled`
for the cross-check.
