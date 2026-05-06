# bmc_circuits — parametric sequential circuits × BMC bound × encoding

27 hand-written sequential circuits, each parametric in bit-width `N`,
encoded under three views of the same circuit:

- `{name}/` — **unrolled BMC**: per-step inputs/latches/gates as
  existentials with linearly-nested deps. O(k·|circ|) vars; result is
  QBF ⊂ DQBF.
- `succinct/{name}/` — **universal step-counter BMC**: step index `t`
  is a `⌈log₂(k+1)⌉`-bit universal, each input/latch/gate is a single
  existential function of `t`, transition asserted once over `(t,t+1)`.
  O(|circ|+log k) vars; genuine DQBF (the two index copies have
  incomparable dep sets). Equisatisfiable with unrolled — see
  `tools/bmc2dqbf/encode_test.py::test_succinct_equisat_with_unrolled`.
- `indinv/{name}/` — **inductive-invariant search** via
  `tools.hwmc2dqbf_indinv.encode_indinv`. k-independent; **SAT here
  means an invariant exists ⇔ property holds**, so for the paired
  circuits `_safe` → SAT, `_bug` → UNSAT.

Default grid: `N ∈ {4,8,12,16,20,24,32}` × `k ∈ {8,24}` → 532 unrolled
+ 532 succinct + 266 indinv = **1330 instances**.

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
python -m benchmarks.train.bmc_circuits.generate            # 1330 instances
... --no-succinct --no-indinv                               # 532 unrolled only
... -N 4,8,12,16,20,24,32 -K 8,16,24 --max-vars 100000
```

## Compare against

The committed `.aag` sources can be fed directly to native HW model
checkers for an apples-to-apples comparison on the same circuits:
**ABC** (`abc -c "read x.aag; bmc3 -F k"` or `pdr`), **nuXmv**
(`read_aiger; check_ltlspec_bmc`), **AVR**, **rIC3**. The runner
registers `abc-bmc` / `abc-pdr` under `domain="hwmc"`. The succinct
encoding has no native counterpart — it is the DQBF-specific
contribution; compare succinct-vs-unrolled within DQBF solvers.

## Alternative encodings

- Unrolled ↔ succinct (this directory).
- Inductive-invariant search: `--indinv` emits via
  `tools/hwmc2dqbf_indinv` (SAT ⇔ property holds; see
  `../hwmc_indinv/`). PR #2 makes this a default subdirectory.
- k-induction: not yet implemented; would lift the succinct encoding
  with a `k`-step antecedent.

## Literature

- Biere et al., *Symbolic Model Checking without BDDs* (TACAS'99) —
  the original BMC.
- Biere–Heljanko–Wieringa, *AIGER 1.9 and Beyond* — the `.aag` format.
- Gitina et al., *Equivalence Checking of Partial Designs Using DQBF*
  (ICCD'13) — the succinct universal-index encoding pattern.
- Bradley, *SAT-Based Model Checking without Unrolling* (VMCAI'11) —
  IC3/PDR, the unbounded baseline.

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
