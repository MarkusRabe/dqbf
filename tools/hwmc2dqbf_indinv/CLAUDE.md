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

## Semantics & cross-encoding consistency

`scripts/indinv_consistency.py` checks every `.aag` in
`benchmarks/train/hwmc_indinv/inductive/` against (a) exhaustive
forward reachability on the AIGER (BFS, up to |L|≤16) and (b) a
fresh BMC@24 encoding of the same circuit, both solved with pedant.

The encoding is **complete**, not just sound: indinv-SAT ⟺ bad
unreachable. Because the reachable set `Reach(s)` is itself an
inductive invariant whenever bad is unreachable, indinv-UNSAT
*implies* bad reachable (no "safe but no inductive invariant"
gap). So the consistency rule is symmetric:

| ground truth | indinv | BMC@k |
|---|---|---|
| bad reachable at depth d | UNSAT | SAT iff k ≥ d |
| bad unreachable | SAT | UNSAT for all k |

All 45 instances pass (0 flagged; 27 with ground truth, 18 by
indinv↔BMC consistency only). The `(s=s'→inv↔inv')` consistency
clause is load-bearing — empirically verified that dropping it
flips `counter_n2` from UNSAT to SAT (unsound).

## Trace extraction from indinv-UNSAT

**Not directly recoverable from solver output.** Pedant emits
nothing on UNSAT; frust's arbsolve-UNSAT path bails without a
candidate. A `.frp` refutation (once frust emits one) would encode
the trace structurally — each application of consecution
`inv∧TRANS→inv'` in the proof corresponds to one transition step —
but Q-resolution does not carry universal instantiations
explicitly, so reading the trace off would mean reverse-engineering
which `(s,i,s')` made each ∀-reduction step possible.

**Practical answer**: indinv-UNSAT ⟺ BMC-SAT-at-some-k (by
completeness above), so to get a counterexample trace, hand the
same `.aag` to `tools.bmc2dqbf.encode` at increasing k and read the
trace from the BMC SAT model. The `depth` column emitted by
`indinv_consistency.py` gives the exact k to use when |L|≤16.
