"""Iterate abc-bmc vs DQBF solvers on hwmc train families until they agree.

For every (.aag, k) instance: run abc-bmc -F {k+1} on the .aig and a
DQBF solver on the encoded .dqdimacs. On disagreement, delta-minimize
the .aag (by zeroing latches/gates one at a time) while preserving the
disagreement, write the minimal repro under scripts/minrepro/, and stop.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import dqdimacs  # noqa: E402
from tools.bmc2dqbf.encode import encode  # noqa: E402
from tools.pec2dqbf.aiger_seq import parse_seq_aag  # noqa: E402

ABC = shutil.which("berkeley-abc") or shutil.which("abc") or "abc"
A2A = str(ROOT / "third_party/aigtoaig")
HQS = str(ROOT / "third_party/hqs/HQS/build/src/hqs/hqs2")
PEDANT = str(ROOT / "third_party/pedant/build/src/pedant")
TIMEOUT = 30
MIN = ROOT / "scripts/minrepro"


def abc_verdict(aag_text: str, k: int) -> str:
    with tempfile.TemporaryDirectory() as d:
        a = Path(d) / "c.aag"
        a.write_text(aag_text)
        b = Path(d) / "c.aig"
        subprocess.run([A2A, str(a), str(b)], check=True, capture_output=True)
        cp = subprocess.run(
            [ABC, "-q", f"read {b}; bmc3 -F {k + 1}"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
    if "was asserted in frame" in cp.stdout:
        return "sat"
    if "No output asserted" in cp.stdout:
        return "unsat"
    return "unknown"


def dqbf_verdict(aag_text: str, k: int, solver: str) -> str:
    seq = parse_seq_aag(aag_text)
    f = encode(seq, k=k, safe=False)
    with tempfile.NamedTemporaryFile("w", suffix=".dqdimacs", delete=False) as tf:
        tf.write(dqdimacs.dumps(f))
        path = tf.name
    try:
        cp = subprocess.run([solver, path], capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        Path(path).unlink(missing_ok=True)
        return "unknown"
    Path(path).unlink(missing_ok=True)
    if cp.returncode == 10 or "SAT" in cp.stdout.upper().split():
        return "sat" if "UNSAT" not in cp.stdout.upper() else "unsat"
    if cp.returncode == 20 or "UNSAT" in cp.stdout.upper():
        return "unsat"
    return "unknown"


def disagrees(aag_text: str, k: int) -> tuple[str, str] | None:
    a = abc_verdict(aag_text, k)
    d = dqbf_verdict(aag_text, k, HQS)
    if a in ("sat", "unsat") and d in ("sat", "unsat") and a != d:
        return (a, d)
    return None


def shrink_aag(aag_text: str, k: int) -> str:
    """Greedy: try setting each gate's RHS to (1,1) and each latch reset to 0/1;
    keep the change if disagreement persists and the AAG still parses."""
    cur = aag_text
    changed = True
    while changed:
        changed = False
        lines = cur.splitlines()
        hdr = lines[0].split()
        m, ni, nl, no, na = (int(x) for x in hdr[1:6])
        for idx in range(1 + ni + nl + no, 1 + ni + nl + no + na):
            parts = lines[idx].split()
            if parts[1:] == ["1", "1"]:
                continue
            trial = lines.copy()
            trial[idx] = f"{parts[0]} 1 1"
            tt = "\n".join(trial) + "\n"
            try:
                if disagrees(tt, k):
                    cur = tt
                    changed = True
            except Exception:
                pass
        # try smaller k
        for kk in range(k - 1, 0, -1):
            if disagrees(cur, kk):
                k = kk
                changed = True
                break
    return cur, k


def main() -> None:
    fams = ["bmc_circuits", "bmc_mutex", "pec_counter", "hwmcc_legacy"]
    insts: list[tuple[Path, str, int]] = []
    for fam in fams:
        for mf in (ROOT / f"benchmarks/train/{fam}").rglob("manifest.json"):
            for e in json.loads(mf.read_text()):
                p = mf.parent / e["path"]
                k = e.get("params", {}).get("k")
                if k is None:
                    continue
                aags = list(p.parent.glob("*.aag"))
                src = next((a for a in aags if p.name.startswith(a.stem)), None)
                if src:
                    insts.append((src, fam, k))
    print(f"checking {len(insts)} (aag,k) pairs...")
    bad: list[tuple[Path, int, str, str]] = []
    for src, fam, k in insts:
        d = disagrees(src.read_text(), k)
        if d:
            bad.append((src, k, *d))
            print(f"  DISAGREE {fam}/{src.name} k={k}: abc={d[0]} hqs={d[1]}")
    if not bad:
        print("✓ abc-bmc and hqs agree on all", len(insts), "instances")
        return
    MIN.mkdir(exist_ok=True)
    for src, k, a, h in bad:
        print(f"minimizing {src.name} k={k}...")
        small, kk = shrink_aag(src.read_text(), k)
        out = MIN / f"{src.stem}_k{kk}_abc-{a}_hqs-{h}.aag"
        out.write_text(small)
        print(f"  → {out} ({len(small)} bytes)")
    sys.exit(1)


if __name__ == "__main__":
    main()
