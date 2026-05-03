"""Harder random BV/EQFOB: width 4. Thin wrapper over random_bv batch mode."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = HERE.parent / "random_bv" / "generate.py"


def main() -> None:
    subprocess.run(
        [
            sys.executable,
            str(GEN),
            "--width",
            "6",
            "--mode",
            "all",
            "--out",
            str(HERE),
            "--n-instances",
            "15",
            "--seed",
            "9000",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
