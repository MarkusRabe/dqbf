# benchmarks/runner/ — parallel benchmark harness

Run one or more solvers over a benchmark family on a many-core box,
collect wall-clock per instance, verify certificates, and render result
tables / plots.

```
manifest.py      discover/load family manifests
run.py           single-solver process pool, JSONL sink
solvers.py       solver registry (forkres, cadet, caqe, rareqs)
multi.py         multi-solver runner with per-job CPU-affinity slot,
                 cert collection + verification
multi_report.py  HTML report: per-family %, SAT/UNSAT split, cactus,
                 pairwise scatter, cert-verification table, disagreements
compare.py       baseline.jsonl vs candidate.jsonl → Δsolved/regressions
report.py        plain-text per-family summary table
cli.py           dqbf-bench {run,multi,table,compare}
```

## Design

- **Manifest-driven.** Each family directory has (or generates) a
  `manifest.json`: `[{"path", "expected": "sat|unsat|unknown",
  "tags": [...]}]`.
- **Exit-code convention.** `10 = SAT`, `20 = UNSAT`, `30/0 = UNKNOWN`.
- **Process pool** (`-j N`, default = ncpu); per-job timeout (default
  10s); `multi` additionally pins each job to a CPU-affinity slot so
  parallel solvers don't contend.
- **Result classes:** `ok`, `wrong` (disagrees with manifest),
  `timeout`, `error` (non-{0,10,20,30} exit), `unknown`.

## CLI

```
dqbf-bench run     --family test/dqbf_qbflib --prover forkres -j 64 --timeout 300
dqbf-bench multi   --root benchmarks/train/random_qbf \
                   --solvers forkres,cadet,caqe,rareqs --verify-certs \
                   -o results/r.jsonl --report results/r.html
dqbf-bench table   results.jsonl --group-by family
dqbf-bench compare baseline.jsonl candidate.jsonl
```

## References

- cadet `scripts/tester.py`:
  https://github.com/MarkusRabe/cadet/blob/master/scripts/tester.py
- QBFEVAL scoring rules: https://qbf23.pages.sai.jku.at/gallery/

## Plan

- [x] `manifest.py`, `run.py`, `report.py`, `cli.py`, self-test.
- [x] `multi`/`compare`/`multi_report` (multi-solver, HTML, plots).
- [ ] Peak-RSS capture (e.g. via `resource.getrusage` in the child).
