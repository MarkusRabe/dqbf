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
@click.option("--family", required=True, help="path under benchmarks/, e.g. test/dqbf_qbflib")
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


@main.command("compare")
@click.argument("baseline", type=click.Path(exists=True))
@click.argument("candidate", type=click.Path(exists=True))
def compare_cmd(baseline: str, candidate: str) -> None:
    from benchmarks.runner.compare import compare, load, render

    cmp = compare(load(baseline), load(candidate))
    print(render(cmp))
    sys.exit(0 if cmp["accept"] else 1)


@main.command("multi")
@click.option("--root", required=True, type=click.Path(exists=True))
@click.option("--solvers", default="forkres,cadet,caqe,rareqs")
@click.option("-j", "--jobs", default=os.cpu_count() or 1, type=int)
@click.option("--timeout", "timeout_s", default=10.0, type=float)
@click.option("-o", "--out", default="results/multi.jsonl", type=click.Path())
@click.option("--report", "report_out", default="results/multi.html", type=click.Path())
@click.option("--certdir", default="results/certs", type=click.Path())
@click.option("--verify-certs", is_flag=True)
def multi_cmd(
    root: str,
    solvers: str,
    jobs: int,
    timeout_s: float,
    out: str,
    report_out: str,
    certdir: str,
    verify_certs: bool,
) -> None:
    from pathlib import Path

    from benchmarks.runner.multi import run_multi
    from benchmarks.runner.multi import verify_certs as do_verify
    from benchmarks.runner.multi_report import render

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(certdir).mkdir(parents=True, exist_ok=True)
    rows = run_multi(Path(root), solvers.split(","), timeout_s, jobs, Path(certdir), Path(out))
    if verify_certs:
        do_verify(rows)
        with open(out, "w") as f:
            for r in rows:
                f.write(__import__("json").dumps(asdict(r)) + "\n")
    render([asdict(r) for r in rows], Path(report_out), timeout_s)


if __name__ == "__main__":
    main()
