# bmc_mutex — superseded by `bmc_circuits/mutex/`

Single-circuit BMC of the fixed-priority mutex over (n requesters ×
bound k). All instances are UNSAT (the arbiter is mutual-exclusion
correct by construction). Kept as a focused difficulty ramp; the same
circuit also appears under `bmc_circuits/mutex/` and
`bmc_circuits/succinct/mutex/` at the consolidated grid.

Encoding/tools/literature: see [`../bmc_circuits/`](../bmc_circuits/README.md).
