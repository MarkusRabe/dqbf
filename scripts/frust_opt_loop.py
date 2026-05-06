"""Per-iteration probe for frust optimization.

Runs frust over a benchmark slice, verifies every certificate, and
prints the slowest instance that's *small* (sorted by wall_time/n_vars
to find "surprisingly slow" cases).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BIN = ROOT / "provers/frust/target/release/frust"
TIMEOUT = 10.0


def n_vars_of(path: Path) -> int:
    op = gzip.open if path.suffix == ".gz" else open
    with op(path, "rt") as f:
        for ln in f:
            if ln.startswith("p cnf"):
                return int(ln.split()[2])
    return 0


def run_one(path: Path) -> dict:
    h = hashlib.sha1(str(path).encode()).hexdigest()[:8]
    cert = Path(f"/tmp/frust_{path.stem}_{h}.aag")
    frp = Path(f"/tmp/frust_{path.stem}_{h}.frp")
    cert.unlink(missing_ok=True)
    frp.unlink(missing_ok=True)
    t0 = time.monotonic()
    cmd = [str(BIN), str(path), "--timeout", str(TIMEOUT)]
    cmd += ["--cert", str(cert), "--proof", str(frp)]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT + 2)
        rc = cp.returncode
    except subprocess.TimeoutExpired:
        rc = 0
    wall = time.monotonic() - t0
    nv = n_vars_of(path)
    cert_status = "n/a"
    vcnf = Path(f"/tmp/frust_{h}_v.cnf")
    if rc == 10 and cert.exists():
        vc = [sys.executable, "-m", "tools.verify.cli", "sat", str(path), str(cert)]
        vc += ["-o", str(vcnf), "--solve"]
        v = subprocess.run(vc, capture_output=True, text=True, cwd=ROOT)
        cert_status = (
            "valid"
            if v.stdout.strip().endswith("VALID") and "INVALID" not in v.stdout
            else "INVALID"
        )
    elif rc == 20 and frp.exists():
        v = subprocess.run(
            [sys.executable, "-m", "tools.verify.cli", "unsat", str(path), str(frp)],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        cert_status = (
            "valid"
            if v.stdout.strip().endswith("VALID") and "INVALID" not in v.stdout
            else "INVALID"
        )
    cert.unlink(missing_ok=True)
    frp.unlink(missing_ok=True)
    vcnf.unlink(missing_ok=True)
    return {
        "path": str(path.relative_to(ROOT)),
        "n_vars": nv,
        "rc": rc,
        "got": {10: "sat", 20: "unsat"}.get(rc, "unknown"),
        "wall_s": round(wall, 4),
        "cert": cert_status,
        "surprise": round(wall / max(nv, 1), 5),
    }


def main() -> None:
    insts: list[Path] = []
    for fam in ["tests/integration/tiny", "benchmarks/train"]:
        for ext in ("*.dqdimacs", "*.dqdimacs.gz", "*.qdimacs"):
            insts += sorted((ROOT / fam).rglob(ext))
    print(f"running {len(insts)} instances on {BIN.name}...", flush=True)
    results = []
    with ProcessPoolExecutor(max_workers=48) as ex:
        for fut in as_completed([ex.submit(run_one, p) for p in insts]):
            results.append(fut.result())
            if len(results) % 200 == 0:
                print(f"  [{len(results)}/{len(insts)}]", flush=True)
    n_sat = sum(1 for r in results if r["got"] == "sat")
    n_unsat = sum(1 for r in results if r["got"] == "unsat")
    n_unk = sum(1 for r in results if r["got"] == "unknown")
    invalid = [r for r in results if r["cert"] == "INVALID"]
    no_cert = [r for r in results if r["got"] in ("sat", "unsat") and r["cert"] == "n/a"]
    print(f"\nsolved: sat={n_sat} unsat={n_unsat} unknown={n_unk}")
    print(f"INVALID certs: {len(invalid)}   missing certs: {len(no_cert)}")
    for r in invalid:
        print(f"  !! {r['path']}: {r['got']} cert INVALID")
    for r in no_cert[:5]:
        print(f"  (no cert) {r['path']}: {r['got']}")
    print("\nSlowest small instances (by wall/n_vars):")
    for r in sorted(results, key=lambda r: -r["surprise"])[:10]:
        print(
            f"  {r['wall_s']:6.2f}s nv={r['n_vars']:5d} sur={r['surprise']:.4f} "
            f"{r['got']:7s} {r['path']}"
        )
    out = Path("/tmp/frust_probe.jsonl")
    if out.exists():
        old = {r["path"]: r["got"] for r in (json.loads(ln) for ln in out.read_text().splitlines())}
        gained = [
            r["path"]
            for r in results
            if r["got"] in ("sat", "unsat") and old.get(r["path"]) == "unknown"
        ]
        lost = [
            r["path"]
            for r in results
            if r["got"] == "unknown" and old.get(r["path"]) in ("sat", "unsat")
        ]
        if gained or lost:
            print(f"\nDiff vs previous run: +{len(gained)} -{len(lost)}")
            for p in gained[:5]:
                print(f"  + {p}")
            for p in lost[:5]:
                print(f"  - {p}")
    out.write_text("\n".join(json.dumps(r) for r in results))


if __name__ == "__main__":
    main()
