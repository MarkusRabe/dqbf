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
| 0 | — | naive O(n²) saturation, BTreeSet clauses | baseline | — |
