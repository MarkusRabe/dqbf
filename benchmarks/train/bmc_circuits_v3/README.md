# bmc_circuits_v3 — wider widths, new circuits, balanced safe/bug

Third iteration of the parametric-circuit BMC family. Strict superset
of v1/v2 at a wider grid:

1. **11 new circuit types** not in v1/v2 — see table below.
2. **All 16 v1+v2 circuits** regenerated under `legacy_*/` (safe-only).
3. **Wider sweep**: `N ∈ {4,8,12,16,20,24,32}` × `k ∈ {8,24}`.
4. **Paired safe/bug variants** per new `(circuit, N)`. The `_safe`
   AIGER satisfies its property (BMC is UNSAT for every k); the `_bug`
   AIGER has one localised fault with a known reachability depth
   `k_bad`, so `expected = sat if k ≥ k_bad else unsat` is set
   **by construction**.

Default grid: 532 instances — 308 new (11 × 7 × 2 × 2; 190 UNSAT /
118 SAT; 253–36k vars) + 224 legacy (16 × 7 × 2; expected=unknown).

## Circuits

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

## Generate

```bash
python -m benchmarks.train.bmc_circuits_v3.generate          # 532 instances
# extras
... --indinv                        # +154 inductive-invariant variants
... -N 4,8,12,16,20,24,32 -K 8,16,24 --max-vars 100000
```

`--indinv` feeds each `.aag` through
`tools/hwmc2dqbf_indinv/encode.py::encode_indinv_aig` (one instance per
`(circuit, N, variant)`; expected = unknown).

## Pipeline

Same as v1: `circuits_v3.py` → `.aag` → `parse_seq_aag` →
`encode(seq, k)` → `.dqdimacs.gz`. Circuit semantics and `k_bad`
derivations are in the docstrings of
[`tools/bmc2dqbf/circuits_v3.py`](../../../tools/bmc2dqbf/circuits_v3.py);
each is verified by simulation in `circuits_v3_test.py`.
