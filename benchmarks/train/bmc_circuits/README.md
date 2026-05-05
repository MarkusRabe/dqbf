# bmc_circuits — parametric sequential circuits × BMC bound × encoding

27 hand-written sequential circuits, each parametric in bit-width `N`,
encoded as bounded model checking at bound `k`. Two encodings of the
same circuits, side by side:

- `{name}/` — **unrolled**: per-step inputs/latches/gates as
  existentials with linearly-nested deps. O(k·|circ|) vars; result is
  QBF ⊂ DQBF.
- `succinct/{name}/` — **universal step-counter**: step index `t` is a
  `⌈log₂(k+1)⌉`-bit universal, each input/latch/gate is a single
  existential function of `t`, transition asserted once over `(t,t+1)`.
  O(|circ|+log k) vars; genuine DQBF (the two index copies have
  incomparable dep sets). Equisatisfiable with unrolled — see
  `tools/bmc2dqbf/encode_test.py::test_succinct_equisat_with_unrolled`.

Default grid: `N ∈ {4,8,12,16,20,24,32}` × `k ∈ {8,24}` → 532 unrolled
+ 532 succinct = **1064 instances**.

## Circuits

### Paired safe/bug (11)

Each `(circuit, N)` emits `_safe` (UNSAT for every k) and `_bug` (one
localised fault, known reachability depth `k_bad`; `expected = sat if
k ≥ k_bad else unsat` — set by construction).

| name | property (bad =) | bug | k_bad |
|---|---|---|---|
| `traffic` | EW-green directly after NS-green | phase advance skips yellow | 2ⁿ |
| `crc` | CRC register ≠ identically-tapped shadow | shadow feedback drops `d` | 1 |
| `lzc` | leading-zero count > n | all-zero arm outputs n+1 | 1 |
| `barrel` | rotate-by-0 ≠ identity | stage-0 mux stuck-at-1 | 1 |
| `bcd_ctr` | any BCD digit > 9 | digit-0 wrap test off-by-one | 10 |
| `debounce` | stability counter > n | saturation removed | n+1 |
| `spi_ctrl` | done ∧ cnt ≠ n | done fires at cnt = n−1 | n+1 |
| `prio_enc` | valid ∧ ¬input[idx] | encoder ignores top bit | 1 |
| `parity_pipe` | pipelined ⊕-reduce ≠ reference | pipe drops bit 0 | 2 |
| `updown` | underflow at zero | down-saturate removed | 1 |
| `hamming` | two identical regs differ | copy-b bit 0 inverted | 1 |

### Single-variant (16)

Reachability of bad varies with `(N, k)`; `expected = unknown`.

`counter`, `gray`, `mutex`, `shift_reg`, `fifo1`, `alu_add`, `alu4op`,
`cmp_pipe`, `lfsr`, `minmax`, `modmul`, `onehot_fsm`, `ringbuf`,
`rr_arbiter`, `sat_accum`, `uart_tx`.

Per-circuit semantics live in the docstrings of
[`tools/bmc2dqbf/circuits.py`](../../../tools/bmc2dqbf/circuits.py),
[`circuits_v2.py`](../../../tools/bmc2dqbf/circuits_v2.py), and
[`circuits_v3.py`](../../../tools/bmc2dqbf/circuits_v3.py); the v3
circuits are verified by simulation in `circuits_v3_test.py`.

## Generate

```bash
python -m benchmarks.train.bmc_circuits.generate            # 1064 instances
... --no-succinct                                           # 532 unrolled only
... --indinv                                                # +indinv/{name}/ via hwmc2dqbf_indinv
... -N 4,8,12,16,20,24,32 -K 8,16,24 --max-vars 100000
```

## Pipeline

```
tools/bmc2dqbf/circuits*.py:circuit_<name>(n[, bug])  →  ASCII AIGER (.aag)
      │  (committed alongside instances per provenance rules)
      ▼
tools/pec2dqbf/aiger_seq.py:parse_seq_aag()           →  SeqAig
      ▼
tools/bmc2dqbf/encode.py:encode[_succinct](seq, k)    →  Formula
      ▼
core.dqdimacs.dumps()                                 →  .dqdimacs.gz
```
