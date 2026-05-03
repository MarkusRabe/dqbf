#!/usr/bin/env python3
"""Wrapper: parse a .tlsf with our minimal parser and invoke strix on the
extracted (formula, ins, outs). Exit codes 10/20/0 (REALIZABLE/UNREAL/UNK)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.ltlsynth2dqbf.tlsf import TlsfNotSupported, parse  # noqa: E402

STRIX = ROOT / "third_party/strix/strix"


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: run_strix_tlsf.py FILE.tlsf [strix-args...]", file=sys.stderr)
        return 1
    tlsf_path = Path(sys.argv[1])
    extra = sys.argv[2:]
    strix = STRIX
    if not strix.exists():
        alt = Path("/root/opensrc/dqbf/third_party/strix/strix")
        if alt.exists():
            strix = alt
        else:
            print("error: strix binary not found", file=sys.stderr)
            return 1
    try:
        spec = parse(tlsf_path.read_text())
    except TlsfNotSupported as exc:
        print(f"error: TLSF feature not supported by minimal parser: {exc}", file=sys.stderr)
        return 1
    formula = spec.ltl_formula()
    cmd = [str(strix), "-f", formula, "-r"]
    if spec.inputs:
        cmd += ["--ins", ",".join(spec.inputs)]
    if spec.outputs:
        cmd += ["--outs", ",".join(spec.outputs)]
    cmd += extra
    cp = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(cp.stdout)
    sys.stderr.write(cp.stderr)
    out = cp.stdout.strip()
    if "UNREALIZABLE" in out:
        return 20
    if "REALIZABLE" in out:
        return 10
    return 0


if __name__ == "__main__":
    sys.exit(main())
