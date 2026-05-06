"""Cross-check the inductive-invariant encoding against BMC and against
ground-truth reachability.

For each `.aag` source under `benchmarks/train/hwmc_indinv/inductive/`:

  1. Compute ground truth by exhaustive forward reachability on the
     AIGER (BFS over 2^|latches| states; cap at |latches| ≤ 16).
  2. Solve the indinv DQDIMACS with pedant (10 s).
  3. Solve a fresh BMC encoding of the same `.aag` at k = 24 with pedant.

Expected:

  bad reachable    ⇒ indinv UNSAT, BMC@k SAT (if k ≥ shortest trace)
  bad unreachable  ⇒ indinv SAT,   BMC@k UNSAT for all k

Because the reachable set is itself an inductive invariant whenever bad
is unreachable, indinv-UNSAT is *exactly* "bad reachable" — so any
mismatch with ground truth is an encoding bug, not an incompleteness.
"""

from __future__ import annotations

import gzip
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from core import dqdimacs
from tools.bmc2dqbf.encode import encode as encode_bmc
from tools.pec2dqbf.aiger_seq import SeqAig, parse_seq_aag

PEDANT = Path("third_party/pedant/build/src/pedant")
ROOT = Path("benchmarks/train/hwmc_indinv/inductive")
BMC_K = 24


def aig_reachable_bad(circ: SeqAig, cap_latches: int = 16) -> tuple[bool | None, int]:
    """BFS over latch states. Returns (bad_reachable, shortest_trace_len)
    or (None, -1) when |latches| > cap."""
    L = len(circ.latches)
    if L > cap_latches:
        return None, -1

    def sim(state: int, inputs: int) -> tuple[int, bool]:
        val: dict[int, int] = {0: 0}
        for j, lat in enumerate(circ.latches):
            val[lat.lit] = (state >> j) & 1
        for j, ai in enumerate(circ.inputs):
            val[ai] = (inputs >> j) & 1
        for g, a, b in circ.gates:
            va = val[a & ~1] ^ (a & 1)
            vb = val[b & ~1] ^ (b & 1)
            val[g] = va & vb
        nxt = 0
        for j, lat in enumerate(circ.latches):
            nxt |= (val[lat.next & ~1] ^ (lat.next & 1)) << j
        bad = bool(val[circ.bad & ~1] ^ (circ.bad & 1))
        return nxt, bad

    init = 0
    for j, lat in enumerate(circ.latches):
        if lat.reset == 1:
            init |= 1 << j
    n_in = len(circ.inputs)
    seen = {init}
    frontier = [init]
    depth = 0
    while frontier:
        nf: list[int] = []
        for s in frontier:
            for ibits in range(1 << n_in) if n_in else (0,):
                ns, bad = sim(s, ibits)
                if bad:
                    return True, depth
                if ns not in seen:
                    seen.add(ns)
                    nf.append(ns)
        frontier = nf
        depth += 1
    return False, -1


def solve(f, timeout_s: float = 10.0) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".dqdimacs", delete=False) as fh:
        fh.write(dqdimacs.dumps(f))
        p = fh.name
    try:
        cp = subprocess.run([str(PEDANT), p], capture_output=True, text=True, timeout=timeout_s)
        rc = cp.returncode
    except subprocess.TimeoutExpired:
        return "?"
    finally:
        Path(p).unlink(missing_ok=True)
    return {10: "sat", 20: "unsat"}.get(rc, "?")


def solve_file(gz: Path, timeout_s: float = 10.0) -> str:
    with tempfile.NamedTemporaryFile("wb", suffix=".dqdimacs", delete=False) as fh:
        fh.write(gzip.decompress(gz.read_bytes()))
        p = fh.name
    try:
        cp = subprocess.run([str(PEDANT), p], capture_output=True, text=True, timeout=timeout_s)
        rc = cp.returncode
    except subprocess.TimeoutExpired:
        return "?"
    finally:
        Path(p).unlink(missing_ok=True)
    return {10: "sat", 20: "unsat"}.get(rc, "?")


def check_one(aag_path: Path) -> dict:
    name = aag_path.stem
    circ = parse_seq_aag(aag_path.read_text())
    truth, depth = aig_reachable_bad(circ)
    indinv_gz = aag_path.with_name(f"indinv_{name}.dqdimacs.gz")
    indinv = solve_file(indinv_gz) if indinv_gz.exists() else "n/a"
    bmc = solve(encode_bmc(circ, BMC_K, source=name))
    flag = ""
    # ground truth available → check both encodings against it
    if truth is True:  # bad reachable
        if indinv == "sat":
            flag += "INDINV-WRONG "
        if depth <= BMC_K and bmc == "unsat":
            flag += "BMC-WRONG "
    elif truth is False:  # bad unreachable
        if indinv == "unsat":
            flag += "INDINV-WRONG "
        if bmc == "sat":
            flag += "BMC-WRONG "
    # always: indinv-SAT (proven safe) is incompatible with BMC-SAT (cex)
    if indinv == "sat" and bmc == "sat":
        flag += "CONTRADICTION "
    return {
        "name": name,
        "L": len(circ.latches),
        "I": len(circ.inputs),
        "truth": {True: "reach", False: "safe", None: "?"}[truth],
        "depth": depth,
        "indinv": indinv,
        "bmc": bmc,
        "flag": flag.strip(),
    }


if __name__ == "__main__":
    aags = sorted(ROOT.glob("*.aag"))
    with ProcessPoolExecutor(max_workers=24) as ex:
        rows = list(ex.map(check_one, aags))
    rows.sort(key=lambda r: (r["name"].rsplit("_n", 1)[0], r["L"]))
    print(f"{'circuit':28} {'L':>3} {'I':>3} {'truth':>6} {'d':>3}  indinv  bmc@24  flag")
    bad = 0
    for r in rows:
        d = "" if r["depth"] < 0 else str(r["depth"])
        print(
            f"{r['name']:28} {r['L']:3} {r['I']:3} {r['truth']:>6} {d:>3}  "
            f"{r['indinv']:>6}  {r['bmc']:>6}  {r['flag']}"
        )
        if r["flag"]:
            bad += 1
    print(f"\n{len(rows)} circuits checked, {bad} flagged.")
