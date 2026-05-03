# bmc_circuits — parametric sequential circuits × BMC bound

Six small, hand-written sequential circuits, each parametric in
bit-width `N`, encoded as plain bounded model checking at bound `k`.
Two scaling axes (N, k) per family.

## Pipeline

```
tools/bmc2dqbf/circuits.py:circuit_<name>(n)   →  ASCII AIGER (.aag)
      │  (committed alongside instances per provenance rules)
      ▼
tools/pec2dqbf/aiger_seq.py:parse_seq_aag()    →  SeqAig
      ▼
tools/bmc2dqbf/encode.py:encode(seq, k, safe=False)
      │  per-step primary inputs, latches/gates as existentials with
      │  linearly-nested deps (so the result is QBF ⊂ DQBF)
      ▼
core.dqdimacs.dumps()                          →  .dqdimacs.gz
```

`generate.py` writes one subdirectory per circuit (= one family) with a
`manifest.json`, the `.aag` source per N, and the compiled
`.dqdimacs.gz` per (N, k). With `safe=False` the formula asserts **bad
is reachable in k steps**, so SAT ⇔ some input trace reaches the bad
state at step k; UNSAT ⇔ no trace does.

## Circuits

### `counter/` — n-bit synchronous up-counter, no inputs

Latches hold the counter value (LSB-first); +1 each cycle. Bad =
all-ones. Deterministic: SAT iff `k ≥ 2^N − 1`. At the committed
N∈{2,4,8}, k∈{4,8,16} only the small-N instances are SAT.

### `gray/` — Gray-code generator (binary counter inside), no inputs

Latches are the binary counter; bad = the *Gray-coded* output is
all-ones, i.e. binary value `2^(N-1)`. SAT iff `k ≥ 2^(N-1)`.

### `mutex/` — n-way fixed-priority arbiter, n request inputs

Grants the lowest-index active request; bad = two grants high in the
same cycle. The arbiter is correct, so **UNSAT for every k** — an
"easy safe" baseline.

### `shift_reg/` — n-stage 1-bit shift register, 1 serial input

Bad = the last stage holds 1. SAT iff `k ≥ N` (drive 1 at step 0, it
emerges N cycles later). At the committed grid every instance is SAT.

### `fifo1/` — depth-1 n-bit register vs an identical shadow

Register and shadow share the same write-enable/data path; bad =
register ≠ shadow. **UNSAT for every k.** The point is encoding cost
(n-bit MUX + XOR trees) as N grows.

### `alu_add/` — pipelined n-bit ripple adder vs latched-operand reference

`out' = a+c`, `ref = sa+sc` with `sa,sc` the latched operands; bad =
`out ≠ ref`. **UNSAT for every k.** Two ripple-carry chains per step
make this the heaviest family per N.

## See also

Detailed per-circuit semantics live in the docstrings in
[`tools/bmc2dqbf/circuits.py`](../../../tools/bmc2dqbf/circuits.py).
