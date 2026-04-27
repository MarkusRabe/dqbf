from __future__ import annotations

import os
import sys
from dataclasses import asdict

import click

from benchmarks.runner.manifest import load_family
from benchmarks.runner.report import load_jsonl, summarize
from benchmarks.runner.run import run_many, write_jsonl

PROVERS = {
    "forkres": [sys.executable, "-m", "provers.forkres.cli", "--timeout", "{timeout}"],
}


@click.group()
def main() -> None:
    pass


@main.command("run")
@click.option("--family", required=True, help="path under benchmarks/, e.g. dqbf/qbfeval")
@click.option("--prover", default="forkres", type=click.Choice(sorted(PROVERS)))
@click.option("-j", "--jobs", default=os.cpu_count() or 1, type=int)
@click.option("--timeout", "timeout_s", default=10.0, type=float)
@click.option("--limit", default=0, type=int, help="cap number of instances (0 = all)")
@click.option("-o", "--out", default="results.jsonl", type=click.Path())
def run_cmd(family: str, prover: str, jobs: int, timeout_s: float, limit: int, out: str) -> None:
    instances = load_family(family)
    if limit:
        instances = instances[:limit]
    cmd = [t.format(timeout=timeout_s) for t in PROVERS[prover]]
    print(f"running {len(instances)} instances with {jobs} jobs, timeout={timeout_s}s")
    results = run_many(instances, cmd, timeout_s + 1.0, jobs, sink=sys.stderr)
    write_jsonl(out, results)
    print(summarize([asdict(r) for r in results]))


@main.command("table")
@click.argument("results", type=click.Path(exists=True))
@click.option("--group-by", default="family")
def table_cmd(results: str, group_by: str) -> None:
    print(summarize(load_jsonl(results), group_by=group_by))


if __name__ == "__main__":
    main()
