# benchmarks/runner/ — parallel benchmark harness

Run a prover over a benchmark family on a many-core box, collect
wall-clock + peak RSS per instance, and render per-family result tables.

## Design

Modeled on cadet's `scripts/tester.py`:

- **Manifest-driven.** Each family directory has (or generates) a
  `manifest.json`: `[{"path": "...", "expected": "sat|unsat|unknown",
  "tags": [...]}]`.
- **Exit-code convention.** `10 = SAT`, `20 = UNSAT`, `30/0 = UNKNOWN`
  (QBFEVAL standard).
- **Process pool** (`-j N`, default = ncpu). Each job wrapped in
  `/usr/bin/time -v` for wall-clock + peak memory; per-job timeout.
- **Result classes:** `ok`, `wrong` (disagrees with manifest),
  `timeout`, `error` (non-{0,10,20,30} exit), `unknown`.
- **Output:** JSONL of raw results + a rendered markdown/CSV table
  grouped by `tags` (family, source, width bucket).

## CLI

```
dqbf-bench run   --family dqbf/qbfeval --prover python -j 64 --timeout 300
dqbf-bench run   --family eqfob/bitwidth_scaling --prover rust -j 64 -D N=2,4,8,16
dqbf-bench table results.jsonl --group-by family --metric solved,median_time
```

## References

- cadet `scripts/tester.py`:
  https://github.com/MarkusRabe/cadet/blob/master/scripts/tester.py
- QBFEVAL scoring rules: https://qbf23.pages.sai.jku.at/gallery/

## Plan

- [ ] `manifest.py` — discover/load/generate manifests; for `eqfob/*`
      call the family's `generate.py`.
- [ ] `run.py` — pool, timeout, `/usr/bin/time -v` parse, JSONL sink.
- [ ] `report.py` — JSONL → grouped table (markdown + CSV); cactus plot.
- [ ] `cli.py` wiring the above.
- [ ] Self-test: tiny family + a stub "prover" that echoes the expected
      result; CI runs this.
