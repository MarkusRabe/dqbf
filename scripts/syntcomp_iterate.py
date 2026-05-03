"""Compare strix (on .tlsf) vs a DQBF solver (on the encoded .dqdimacs)
for the syntcomp_legacy family. Mirrors hwmc_iterate.py.

Semantics note: the DQBF encoding is bounded — SAT ⇒ REALIZABLE, but
UNSAT at a given (n,k) is *not* UNREALIZABLE. So the only true
disagreement is **DQBF SAT vs strix UNREALIZABLE** (or strix-REALIZABLE
where the spec status says unrealizable). DQBF-UNSAT vs strix-REALIZABLE
just means the bound was too small.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import dqdimacs  # noqa: E402
from tools.ltlsynth2dqbf.encode import encode_tlsf  # noqa: E402
from tools.ltlsynth2dqbf.ltl import LtlParseError  # noqa: E402
from tools.ltlsynth2dqbf.tlsf import TlsfNotSupported  # noqa: E402
from tools.ltlsynth2dqbf.tlsf import parse as parse_tlsf  # noqa: E402

HQS = ROOT / "third_party/hqs/HQS/build/src/hqs/hqs2"
PEDANT = ROOT / "third_party/pedant/build/src/pedant"
STRIX = ROOT / "third_party/strix/strix"
TIMEOUT = 10


def _alt(p: Path) -> Path:
    """Fall back to the parent repo's third_party if running in a worktree."""
    if p.exists():
        return p
    alt = Path("/root/opensrc/dqbf") / p.relative_to(ROOT)
    return alt if alt.exists() else p


def strix_verdict(tlsf: Path) -> str:
    cp = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_strix_tlsf.py"), str(tlsf)],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )
    return {10: "sat", 20: "unsat"}.get(cp.returncode, "unknown")


def dqbf_verdict(tlsf: Path, n: int, k: int, solver: Path) -> str:
    try:
        f = encode_tlsf(tlsf.read_text(), n_states=n, k=k, source=tlsf.name)
    except (TlsfNotSupported, LtlParseError, ValueError):
        return "n/a"
    with tempfile.NamedTemporaryFile("w", suffix=".dqdimacs", delete=False) as tf:
        tf.write(dqdimacs.dumps(f))
        path = tf.name
    try:
        cp = subprocess.run([str(solver), path], capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        Path(path).unlink(missing_ok=True)
        return "unknown"
    Path(path).unlink(missing_ok=True)
    if cp.returncode == 10:
        return "sat"
    if cp.returncode == 20:
        return "unsat"
    return "unknown"


def check_one(tlsf: Path, n: int, k: int) -> dict:
    spec = parse_tlsf(tlsf.read_text())
    sx = "unknown"
    if shutil.which(str(_alt(STRIX))) or _alt(STRIX).exists():
        try:
            sx = strix_verdict(tlsf)
        except subprocess.TimeoutExpired:
            sx = "unknown"
    dq = dqbf_verdict(tlsf, n, k, _alt(HQS))
    # disagreement only when DQBF says SAT but strix says UNREALIZABLE
    disagree = dq == "sat" and sx == "unsat"
    return {
        "tlsf": tlsf.name,
        "n": n,
        "k": k,
        "status": spec.status,
        "strix": sx,
        "dqbf": dq,
        "disagree": disagree,
    }


def main() -> None:
    fams = ["benchmarks/train/syntcomp_legacy/instances"]
    insts: list[tuple[Path, int, int]] = []
    for fam in fams:
        for tlsf in sorted((ROOT / fam).glob("*.tlsf")):
            for n in (2, 4, 8):
                insts.append((tlsf, n, 6))
    jobs = max(1, (os.cpu_count() or 8) * 3 // 4)
    print(f"checking {len(insts)} (tlsf,n) pairs with j={jobs}...")
    rows: list[dict] = []
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        futs = {ex.submit(check_one, t, n, k): (t, n, k) for t, n, k in insts}
        for fut in as_completed(futs):
            try:
                rows.append(fut.result())
            except Exception as e:
                t, n, k = futs[fut]
                print(f"  ERROR {t.name} n={n}: {e!r}")
    bad = [r for r in rows if r["disagree"]]
    print(f"\ndisagreements (DQBF SAT vs strix UNREALIZABLE): {len(bad)}")
    for r in bad:
        print(f"  {r['tlsf']} n={r['n']}: dqbf={r['dqbf']} strix={r['strix']} status={r['status']}")
    realized = sum(1 for r in rows if r["dqbf"] == "sat")
    print(
        f"\nDQBF SAT (⇒realizable witness found): {realized}/{len(rows)} "
        f"| strix realizable: {sum(1 for r in rows if r['strix'] == 'sat')}"
    )
    Path("/tmp/syntcomp_iterate.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
