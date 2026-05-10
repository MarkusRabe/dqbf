"""Random DQBF fuzzer: generate small instances, run frust, verify.

Generates random DQBF formulas with structure that exercises the
const-partner cell-link path (multiple existentials with overlapping
dep sets) and runs frust → verify in a loop. Any INVALID cert or
verdict-vs-pedant mismatch is a soundness bug.

Run for N seconds (default 300):
    python -m scripts.fuzz_frust [seconds] [--strict]
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRUST = ROOT / "provers" / "frust" / "target" / "release" / "frust"
PEDANT = ROOT / "third_party" / "pedant" / "build" / "src" / "pedant"


def gen_dqdimacs(rng: random.Random) -> str:
    """A small random DQBF biased toward shapes that exercise the
    const-partner cell-link path: a handful of universals, a few
    existentials with *overlapping but distinct* dep sets, and clauses
    that mix universal and existential literals so the matrix has a
    non-trivial structure but is small enough to solve in <1 s."""
    nu = rng.randint(2, 5)
    ne = rng.randint(2, 6)
    universals = list(range(1, nu + 1))
    existentials = list(range(nu + 1, nu + ne + 1))
    # Each existential gets a random subset of universals as deps.
    deps = {y: rng.sample(universals, rng.randint(0, nu)) for y in existentials}
    nv = nu + ne
    lines = ["c fuzz_frust"]
    lines.append(f"p cnf {nv} 0")  # clause count fixed up later
    lines.append("a " + " ".join(map(str, universals)) + " 0")
    for y in existentials:
        lines.append(f"d {y} " + " ".join(map(str, sorted(deps[y]))) + " 0")
    # Random 2-4-literal clauses over all vars.
    nc = rng.randint(2 * nv, 4 * nv)
    clauses: list[list[int]] = []
    for _ in range(nc):
        k = rng.randint(2, 4)
        vs = rng.sample(range(1, nv + 1), min(k, nv))
        clauses.append([v * rng.choice([1, -1]) for v in vs])
    lines[1] = f"p cnf {nv} {len(clauses)}"
    lines.extend(" ".join(map(str, c)) + " 0" for c in clauses)
    return "\n".join(lines) + "\n"


def fuzz(seconds: float, strict: bool) -> int:
    rng = random.Random()
    deadline = time.time() + seconds
    n = bad = 0
    flag = ["--strict-cell-link"] if strict else []
    while time.time() < deadline:
        n += 1
        text = gen_dqdimacs(rng)
        with tempfile.NamedTemporaryFile("w", suffix=".dqdimacs", delete=False) as fh:
            fh.write(text)
            path = fh.name
        cert = path + ".aag"
        proof = path + ".frp"
        try:
            cp = subprocess.run(
                [str(FRUST), path, "--timeout", "2", "--cert", cert, "--proof", proof, *flag],
                capture_output=True,
                timeout=5,
            )
            rc = cp.returncode
        except subprocess.TimeoutExpired:
            rc = -1
        verdict = "sat" if rc == 10 else ("unsat" if rc == 20 else "unknown")
        problem = None
        # Verify cert when present.
        if rc == 10 and os.path.exists(cert):
            v = subprocess.run(
                [
                    sys.executable, "-m", "tools.verify.cli", "sat",
                    path, cert, "-o", "/dev/null", "--solve",
                ],
                cwd=ROOT, capture_output=True, text=True, timeout=10,
            )
            if "INVALID" in v.stdout + v.stderr:
                problem = f"INVALID SAT cert: {v.stdout.strip()[:200]}"
        elif rc == 20 and os.path.exists(proof):
            v = subprocess.run(
                [sys.executable, "-m", "tools.verify.cli", "unsat", path, proof],
                cwd=ROOT, capture_output=True, text=True, timeout=10,
            )
            if "INVALID" in v.stdout + v.stderr:
                problem = f"INVALID UNSAT proof: {v.stdout.strip()[:200]}"
        # Cross-check against pedant when no cert (the soundness gap).
        if problem is None and verdict in ("sat", "unsat") and PEDANT.exists():
            cp2 = subprocess.run([str(PEDANT), path], capture_output=True, timeout=5)
            ped = "sat" if cp2.returncode == 10 else ("unsat" if cp2.returncode == 20 else "?")
            if ped in ("sat", "unsat") and ped != verdict:
                problem = f"VERDICT MISMATCH: frust={verdict} pedant={ped}"
        if problem:
            bad += 1
            keep = ROOT / "tests" / "integration" / "tiny" / f"fuzz_bad_{n}.dqdimacs"
            keep.write_text(text)
            print(f"!! [{n}] {problem}")
            print(f"   instance saved to {keep}")
        for p in (path, cert, proof):
            if os.path.exists(p):
                os.unlink(p)
        if n % 200 == 0:
            print(f"   ... {n} tested, {bad} bad ({time.time() - deadline + seconds:.0f}/{seconds:.0f}s)")
    print(f"\n{'OK' if bad == 0 else 'FAIL'}: {n} instances fuzzed, {bad} soundness bugs")
    return bad


if __name__ == "__main__":
    secs = 300.0
    strict = False
    for a in sys.argv[1:]:
        if a == "--strict":
            strict = True
        else:
            secs = float(a)
    sys.exit(1 if fuzz(secs, strict) else 0)
