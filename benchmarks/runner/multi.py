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

from benchmarks.runner.cache import instance_hash, key, load, solver_hash, store
from benchmarks.runner.solvers import Solver, registry

EXIT = {10: "sat", 20: "unsat", 0: "unknown", 30: "unknown"}

# Note on HW model checkers: abc-bmc/-pdr answer the *unbounded* question
# on the source .aag, while a .dqdimacs instance encodes a *bounded* k. So
# abc may report SAT (bug at frame > k) where the DQBF instance is UNSAT —
# that's a question mismatch, not a solver bug.
_SAT_PATTERNS = [
    re.compile(r"^(s SATISFIABLE|SATISFIABLE|SAT|\[RESULT\]\s+SAT)\s*$", re.MULTILINE),
    re.compile(r"was asserted in frame", re.IGNORECASE),  # abc bmc3
    re.compile(r"^REALIZABLE\s*$", re.MULTILINE),  # synthesis tools
]
_UNSAT_PATTERNS = [
    re.compile(r"^(s UNSATISFIABLE|UNSATISFIABLE|UNSAT|\[RESULT\]\s+UNSAT)\s*$", re.MULTILINE),
    re.compile(r"Property proved|Invariant.*holds", re.IGNORECASE),  # abc pdr
    re.compile(r"No output asserted in \d+ frames"),  # abc bmc3 (bounded UNSAT)
    re.compile(r"^UNREALIZABLE\s*$", re.MULTILINE),  # synthesis tools
]


_ABC_FRAME = re.compile(r"was asserted in frame (\d+)")


def _verdict_from_output(rc: int, stdout: str, k: int | None = None) -> str:
    got = EXIT.get(rc, "error")
    if got != "unknown":
        return got
    for p in _UNSAT_PATTERNS:
        if p.search(stdout):
            return "unsat"
    m = _ABC_FRAME.search(stdout)
    if m:
        frame = int(m.group(1))
        # pdr's counterexample isn't guaranteed shortest, so frame>k tells us
        # nothing about reachability within k.
        return "sat" if (k is None or frame <= k) else "unknown"
    for p in _SAT_PATTERNS:
        if p.search(stdout):
            return "sat"
    return "unknown"


def _find_source(inst: Path, ext: str) -> Path | None:
    """Find the source file (e.g. .aag/.tlsf) by stem prefix.
    Prefer the LONGEST matching stem so 'detector_unreal_n02' picks
    'detector_unreal.tlsf' not 'detector.tlsf'."""
    stem = inst.name.split(".")[0]
    cands = [c for c in inst.parent.glob(f"*{ext}") if stem.startswith(c.stem)]
    return max(cands, key=lambda c: len(c.stem), default=None)


def _find_source_aag(inst: Path) -> Path | None:
    return _find_source(inst, ".aag")


def _find_source_tlsf(inst: Path) -> Path | None:
    return _find_source(inst, ".tlsf")


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
    cached: bool = False


def discover(root: Path) -> list[tuple[Path, str, str, dict]]:
    """Return (path, family, expected, params) for every instance."""
    root_r = root.resolve()
    out: list[tuple[Path, str, str, dict]] = []
    for mf in root.rglob("manifest.json"):
        fam = str(mf.parent.relative_to(root))
        for e in json.loads(mf.read_text()):
            p = (mf.parent / e["path"]).resolve()
            if not p.is_relative_to(root_r):
                continue
            out.append((p, fam, e.get("expected", "unknown"), e.get("params", {})))
    if not out:
        for p in sorted(root.rglob("*.qdimacs")) + sorted(root.rglob("*.dqdimacs")):
            out.append((p, str(p.parent.relative_to(root)), "unknown", {}))
    return out


def _run_one(
    solver: Solver,
    inst: Path,
    family: str,
    expected: str,
    verify: bool,
    params: dict,
    timeout_s: float,
    certdir: Path,
    slot: int,
) -> RunRow:
    stem = Path(inst.stem.replace(".dqdimacs", "").replace(".qdimacs", "")).name
    sub = certdir / solver.name / family.replace("/", "_")
    sub.mkdir(parents=True, exist_ok=True)
    file_path = str(inst)
    inst_ext = inst.name.replace(".gz", "").rsplit(".", 1)[-1]
    if solver.input_format == "qdimacs" and inst_ext != "qdimacs":
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
    if solver.input_format == "tlsf":
        src = _find_source_tlsf(inst)
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
        file_path = str(src)
    elif solver.input_format == "aag":
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
    k = params.get("k")
    fmt = {
        "file": file_path,
        "timeout": str(timeout_s),
        "certdir": str(sub),
        "stem": stem,
        "k": str(k) if k is not None else "1000",
        "kp1": str(k + 1) if isinstance(k, int) else "1001",
    }
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
        got = _verdict_from_output(cp.returncode, cp.stdout, k=params.get("k"))
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
    row = RunRow(
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
    if verify:
        row.cert_status = _verify_one(row, timeout_s)
    return row


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
    verify: bool = False,
    use_cache: bool = True,
) -> list[RunRow]:
    reg = registry()
    solvers = [reg[s] for s in solver_names if reg[s].available]
    skipped = [s for s in solver_names if not reg[s].available]
    if skipped:
        print(f"skipping unavailable solvers: {skipped}")
    instances = discover(root)
    print(f"{len(instances)} instances × {len(solvers)} solvers, timeout={timeout_s}s, j={jobs}")

    shash = {sv.name: solver_hash(sv.cmd) for sv in solvers}
    ihash = {inst: instance_hash(inst) for inst, _, _, _ in instances}

    rows: list[RunRow] = []
    todo: list[tuple[Solver, Path, str, str, dict, str]] = []
    for inst, fam, exp, prm in instances:
        for sv in solvers:
            k = key(shash[sv.name], ihash[inst], timeout_s)
            hit = load(k) if use_cache else None
            if hit is not None:
                hit["cached"] = True
                hit["cert_path"] = None
                # Path/family/expected may have moved or been re-tagged
                # since caching; the verdict is keyed on content, so
                # refresh the metadata from the current discovery.
                hit["path"] = str(inst)
                hit["family"] = fam
                hit["expected"] = exp
                rows.append(RunRow(**hit))
            else:
                todo.append((sv, inst, fam, exp, prm, k))
    print(f"  cache: {len(rows)} hits, {len(todo)} to run")

    with sink_path.open("w") as sink, ProcessPoolExecutor(max_workers=jobs) as ex:
        for r in rows:
            sink.write(json.dumps(asdict(r)) + "\n")
        sink.flush()
        futs = {
            ex.submit(_run_one, sv, inst, fam, exp, verify, prm, timeout_s, certdir, i): k
            for i, (sv, inst, fam, exp, prm, k) in enumerate(todo)
        }
        for fut in as_completed(futs):
            try:
                r = fut.result()
            except FileNotFoundError as e:
                # Instance disappeared mid-run (regenerated by a
                # concurrent process). Skip rather than crash the pool.
                print(f"  skip (vanished): {e}")
                continue
            rows.append(r)
            sink.write(json.dumps(asdict(r)) + "\n")
            sink.flush()
            store(futs[fut], asdict(r))
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


def _verify_one(r: RunRow, timeout_s: float = 10.0) -> str:
    """Return cert_status for a single row via dqbf-verify {sat,unsat}."""
    import sys

    if r.got not in ("sat", "unsat") or not r.cert_path:
        return "n/a"
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
        return "timeout"
    return {0: "valid", 1: "invalid", 2: "dep", 3: "skipped"}.get(rc, "error")


def verify_certs(rows: list[RunRow], timeout_s: float = 10.0) -> None:
    """Mutates rows in place. Kept for back-compat; the runner now
    verifies inside the worker."""
    for r in rows:
        if r.cert_status == "n/a" and r.cert_path:
            r.cert_status = _verify_one(r, timeout_s)
