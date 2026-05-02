"""Multi-solver benchmark: run N solvers over a directory tree, compare,
verify certificates, and emit a JSONL of per-(solver,instance) results.

Each solver invocation is an isolated subprocess with its own wall-clock
timeout (SIGKILL on expiry) and a per-job CPU-affinity slot so parallel
runs don't contend.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

from benchmarks.runner.solvers import Solver, registry

EXIT = {10: "sat", 20: "unsat", 0: "unknown", 30: "unknown"}


@dataclass
class RunRow:
    solver: str
    path: str
    family: str
    expected: str
    got: str
    wall_s: float
    cert_path: str | None
    cert_bytes: int
    cert_status: str  # "n/a" | "valid" | "invalid" | "dep" | "error" | "skipped"


def discover(root: Path) -> list[tuple[Path, str, str]]:
    """Return (path, family, expected) for every *.qdimacs / *.dqdimacs[.gz]."""
    root_r = root.resolve()
    out: list[tuple[Path, str, str]] = []
    for mf in root.rglob("manifest.json"):
        fam = str(mf.parent.relative_to(root))
        for e in json.loads(mf.read_text()):
            p = (mf.parent / e["path"]).resolve()
            if not p.is_relative_to(root_r):
                continue
            out.append((p, fam, e.get("expected", "unknown")))
    if not out:
        for p in sorted(root.rglob("*.qdimacs")) + sorted(root.rglob("*.dqdimacs")):
            out.append((p, str(p.parent.relative_to(root)), "unknown"))
    return out


def _run_one(
    solver: Solver,
    inst: Path,
    family: str,
    expected: str,
    timeout_s: float,
    certdir: Path,
    slot: int,
) -> RunRow:
    stem = Path(inst.stem.replace(".dqdimacs", "").replace(".qdimacs", "")).name
    sub = certdir / solver.name
    sub.mkdir(parents=True, exist_ok=True)
    fmt = {"file": str(inst), "timeout": str(timeout_s), "certdir": str(sub), "stem": stem}
    cmd = [t.format(**fmt) for t in solver.cmd]
    t0 = time.monotonic()
    try:
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s + 1.0,
            preexec_fn=lambda: _affine(slot),
        )
        wall = time.monotonic() - t0
        got = EXIT.get(cp.returncode, "error")
    except subprocess.TimeoutExpired:
        wall = timeout_s
        got = "timeout"
    cert_path: str | None = None
    cert_bytes = 0
    if solver.cert_glob:
        cp_ = Path(solver.cert_glob.format(**fmt))
        if cp_.exists():
            cert_path = str(cp_)
            cert_bytes = cp_.stat().st_size
    return RunRow(
        solver=solver.name,
        path=str(inst),
        family=family,
        expected=expected,
        got=got,
        wall_s=round(wall, 4),
        cert_path=cert_path,
        cert_bytes=cert_bytes,
        cert_status="n/a",
    )


def _affine(slot: int) -> None:
    try:
        n = os.cpu_count() or 1
        os.sched_setaffinity(0, {slot % n})
    except (AttributeError, OSError):
        pass


def run_multi(
    root: Path,
    solver_names: list[str],
    timeout_s: float,
    jobs: int,
    certdir: Path,
    sink_path: Path,
) -> list[RunRow]:
    reg = registry()
    solvers = [reg[s] for s in solver_names if reg[s].available]
    skipped = [s for s in solver_names if not reg[s].available]
    if skipped:
        print(f"skipping unavailable solvers: {skipped}")
    instances = discover(root)
    print(f"{len(instances)} instances × {len(solvers)} solvers, timeout={timeout_s}s, j={jobs}")
    tasks = [
        (sv, inst, fam, exp, i) for i, (inst, fam, exp) in enumerate(instances) for sv in solvers
    ]
    rows: list[RunRow] = []
    with sink_path.open("w") as sink, ProcessPoolExecutor(max_workers=jobs) as ex:
        futs = {
            ex.submit(_run_one, sv, inst, fam, exp, timeout_s, certdir, i): (sv.name, inst)
            for (sv, inst, fam, exp, i) in tasks
        }
        for fut in as_completed(futs):
            r = fut.result()
            rows.append(r)
            sink.write(json.dumps(asdict(r)) + "\n")
            sink.flush()
    return rows


def _adapt_cadet_aag(path: str) -> str:
    """Rewrite cadet's symbol table (bare var IDs) to u<k>/e<k> convention."""
    lines = Path(path).read_text().splitlines()
    out, hdr_seen = [], False
    for ln in lines:
        if ln.startswith("aag "):
            hdr_seen = True
        if hdr_seen and len(ln) > 2 and ln[0] in "io" and " " in ln:
            tag, name = ln.split(" ", 1)
            if name.isdigit():
                ln = f"{tag} {'u' if ln[0] == 'i' else 'e'}{name}"
            elif name == "result":
                continue
        out.append(ln)
    # cadet's header counts the dropped 'result' output; fix the o-count:
    # Actually outputs in the body are unchanged; just dropping the symbol-table
    # entry means output_by_name won't find 'result', which is fine.
    new_path = path + ".adapted"
    Path(new_path).write_text("\n".join(out) + "\n")
    return new_path


CERT_ADAPTERS = {"cadet": _adapt_cadet_aag}


def verify_certs(rows: list[RunRow], timeout_s: float = 5.0) -> None:
    """Mutates rows in place: fills cert_status for SAT certs via dqbf-verify."""
    import sys

    for r in rows:
        if r.got != "sat" or not r.cert_path:
            continue
        cert = r.cert_path
        if r.solver in CERT_ADAPTERS:
            cert = CERT_ADAPTERS[r.solver](cert)
        cnf = r.cert_path + ".verify.cnf"
        cp = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.verify.cli",
                "sat",
                r.path,
                cert,
                "-o",
                cnf,
                "--solve",
            ],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if cp.returncode == 0:
            r.cert_status = "valid"
        elif cp.returncode == 1:
            r.cert_status = "invalid"
        elif cp.returncode == 2:
            r.cert_status = "dep"
        elif cp.returncode == 3:
            r.cert_status = "skipped"  # no SAT backend
        else:
            r.cert_status = "error"
