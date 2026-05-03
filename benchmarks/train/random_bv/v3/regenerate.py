"""v3 random BV/EQFOB: width 8. Thin wrapper over random_bv batch mode."""

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
            "12",
            "--mode",
            "all",
            "--out",
            str(HERE),
            "--n-instances",
            "10",
            "--seed",
            "99000",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
