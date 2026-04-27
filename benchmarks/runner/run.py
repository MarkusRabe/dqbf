"""Run a prover binary over a manifest in a process pool."""

from __future__ import annotations

import json
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO

from benchmarks.runner.manifest import Instance

EXIT_TO_RESULT = {10: "sat", 20: "unsat", 0: "unknown", 30: "unknown"}


@dataclass
class RunResult:
    path: str
    family: str
    expected: str
    got: str
    status: str  # ok | wrong | timeout | error | unknown
    wall_s: float
    exit_code: int


def _classify(expected: str, got: str) -> str:
    if got in ("timeout", "error"):
        return got
    if expected == "unknown":
        return "unknown" if got == "unknown" else "ok"
    if got == "unknown":
        return "unknown"
    return "ok" if got == expected else "wrong"


def run_one(inst: Instance, prover_cmd: list[str], timeout_s: float) -> RunResult:
    t0 = time.monotonic()
    try:
        cp = subprocess.run(
            [*prover_cmd, str(inst.path)],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        wall = time.monotonic() - t0
        got = EXIT_TO_RESULT.get(cp.returncode, "error")
    except subprocess.TimeoutExpired:
        wall = time.monotonic() - t0
        got = "timeout"
        cp_returncode = -1
    else:
        cp_returncode = cp.returncode
    return RunResult(
        path=str(inst.path),
        family=inst.family,
        expected=inst.expected,
        got=got,
        status=_classify(inst.expected, got),
        wall_s=round(wall, 4),
        exit_code=cp_returncode,
    )


def run_many(
    instances: list[Instance],
    prover_cmd: list[str],
    timeout_s: float,
    jobs: int,
    sink: TextIO | None = None,
) -> list[RunResult]:
    results: list[RunResult] = []
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        futs = {ex.submit(run_one, i, prover_cmd, timeout_s): i for i in instances}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            if sink:
                sink.write(json.dumps(asdict(r)) + "\n")
                sink.flush()
    return results


def write_jsonl(path: str | Path, results: list[RunResult]) -> None:
    with open(path, "w") as f:
        for r in results:
            f.write(json.dumps(asdict(r)) + "\n")
