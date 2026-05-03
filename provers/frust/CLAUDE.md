# provers/frust/ — standalone Rust DQBF solver

Single-threaded fork-resolution prover. **No code shared** with the
rest of the repo: own DQDIMACS parser, own rule implementations, own
`.frp`/`.aag` writers. The Python verifier in `tools/verify/` is the
correctness oracle.

## Build & run

```sh
cargo build --release --manifest-path provers/frust/Cargo.toml
target/release/frust FILE.dqdimacs[.gz] --timeout 10 \
  --cert out.aag --proof out.frp
```

Exit codes 10/20/0 (sat/unsat/unknown).

## Iteration log

| iter | bottleneck instance | observation | change | result |
|---|---|---|---|---|
| 0 | — | naive O(n²) saturation, BTreeSet clauses | baseline | 154/344, 0 invalid |
| 1 | `2qbf_s0001` (9 vars, 10s) | 51% in `resolve`; whole-db clone per item | Vec\<i32\> clauses + occurrence lists | 194/344, 0 invalid; instance still 10s (clause-space explosion) |
| 2 | same | 13270 clauses ≈ 2/3 of 3⁹ clause space | forward+backward subsumption via occ lists | 225/344, 0 invalid; instance now **7ms** (445 clauses) |
| 3 | `inc_n4` (36v, 95cl, 10s) | 48% in `activate` (subsumption); long occ lists | u64 signature fast-reject + shortest-first priority queue | 261/344, 0 invalid; instance still 10s (Tseitin saturation explodes) |
