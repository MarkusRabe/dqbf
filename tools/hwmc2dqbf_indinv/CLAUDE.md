# tools/hwmc2dqbf_indinv

Sequential AIGER → DQBF encoding the **inductive-invariant** search.
Dual of `../bmc2dqbf/` (which encodes bounded reachability).

- `encode.py::encode_indinv` — the construction; see module docstring
  for the DQBF shape and the `(s=s') → (inv↔inv')` same-function trick.
- `circuits_buggy.py` — fault-injected mutex/fifo1/alu_add so the
  family has UNSAT instances by construction.
- `encode_test.py` — brute-force `core.semantics.is_true` on 1-latch
  circuits; hqs cross-check on 2-bit circuits.

Reuses `tools.pec2dqbf.aiger_seq` for AIGER I/O and
`tools.bmc2dqbf.circuits` for the source circuits.
