"""Multi-solver benchmark: run N solvers over a directory tree, compare,
verify certificates, and emit a JSONL of per-(solver,instance) results.

Each solver invocation is an isolated subprocess with its own wall-clock
timeout (SIGKILL on expiry) and a per-job CPU-affinity slot so parallel
runs don't contend.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

from benchmarks.runner.solvers import Solver, registry

EXIT = {10: "sat", 20: "unsat", 0: "unknown", 30: "unknown"}

# Note on HW model checkers: abc-bmc/-pdr answer the *unbounded* question
# on the source .aag, while a .dqdimacs instance encodes a *bounded* k. So
# abc may report SAT (bug at frame > k) where the DQBF instance is UNSAT —
# that's a question mismatch, not a solver bug.
_SAT_PATTERNS = [
    re.compile(r"^(s SATISFIABLE|SATISFIABLE|SAT|\[RESULT\]\s+SAT)\s*$", re.MULTILINE),
    re.compile(r"was asserted in frame", re.IGNORECASE),  # abc bmc3
]
_UNSAT_PATTERNS = [
    re.compile(r"^(s UNSATISFIABLE|UNSATISFIABLE|UNSAT|\[RESULT\]\s+UNSAT)\s*$", re.MULTILINE),
    re.compile(r"Property proved|Invariant.*holds", re.IGNORECASE),  # abc pdr
]


def _verdict_from_output(rc: int, stdout: str) -> str:
    got = EXIT.get(rc, "error")
    if got != "unknown":
        return got
    for p in _UNSAT_PATTERNS:
        if p.search(stdout):
            return "unsat"
    for p in _SAT_PATTERNS:
        if p.search(stdout):
            return "sat"
    return "unknown"


def _find_source_aag(inst: Path) -> Path | None:
    """For families that commit the .aag source alongside the compiled
    .dqdimacs, find the matching source by stem prefix."""
    stem = inst.name.split(".")[0]
    for cand in inst.parent.glob("*.aag"):
        if stem.startswith(cand.stem):
            return cand
    return None


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
    file_path = str(inst)
    if solver.input_format == "aag":
        src = _find_source_aag(inst)
        if src is None:
            return RunRow(
                solver=solver.name,
                path=str(inst),
                family=family,
                expected=expected,
                got="n/a",
                wall_s=0.0,
                cert_path=None,
                cert_bytes=0,
                cert_status="n/a",
            )
        aig = sub / f"{src.stem}.aig"
        if not aig.exists():
            a2a = Path(__file__).resolve().parents[2] / "third_party/aigtoaig"
            subprocess.run([str(a2a), str(src), str(aig)], check=True, capture_output=True)
        file_path = str(aig)
    elif inst.suffix == ".gz":
        import gzip

        plain = sub / f"{stem}.in"
        plain.write_bytes(gzip.decompress(inst.read_bytes()))
        file_path = str(plain)
    # Some solver templates (abc -q "...") embed {file} inside an interpreted
    # command string; refuse paths that could break out of that.
    if not re.fullmatch(r"[A-Za-z0-9_./+\-]+", file_path):
        return RunRow(
            solver=solver.name,
            path=str(inst),
            family=family,
            expected=expected,
            got="error",
            wall_s=0.0,
            cert_path=None,
            cert_bytes=0,
            cert_status="n/a",
        )
    fmt = {"file": file_path, "timeout": str(timeout_s), "certdir": str(sub), "stem": stem}
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
        got = _verdict_from_output(cp.returncode, cp.stdout)
    except subprocess.TimeoutExpired:
        wall = timeout_s
        got = "timeout"
    cert_path: str | None = None
    cert_bytes = 0
    tmpl = solver.certs.get(got)
    if tmpl:
        cp_ = Path(tmpl.format(**fmt))
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


CERT_ADAPTERS = {"cadet": _adapt_cadet_aag, "pedant": _adapt_cadet_aag}


def verify_certs(rows: list[RunRow], timeout_s: float = 10.0) -> None:
    """Mutates rows in place: fills cert_status via dqbf-verify {sat,unsat}."""
    import sys

    for r in rows:
        if r.got not in ("sat", "unsat") or not r.cert_path:
            continue
        cert = r.cert_path
        if r.solver in CERT_ADAPTERS and r.got == "sat":
            cert = CERT_ADAPTERS[r.solver](cert)
        if r.got == "sat":
            cmd = [
                sys.executable,
                "-m",
                "tools.verify.cli",
                "sat",
                r.path,
                cert,
                "-o",
                r.cert_path + ".verify.cnf",
                "--solve",
            ]
        else:
            cmd = [sys.executable, "-m", "tools.verify.cli", "unsat", r.path, cert]
        try:
            cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
            rc = cp.returncode
        except subprocess.TimeoutExpired:
            r.cert_status = "timeout"
            continue
        if rc == 0:
            r.cert_status = "valid"
        elif rc == 1:
            r.cert_status = "invalid"
        elif rc == 2:
            r.cert_status = "dep"
        elif rc == 3:
            r.cert_status = "skipped"
        else:
            r.cert_status = "error"
