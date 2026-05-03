"""v3 bitwidth scaling: same op sweep as v1 at widths 8,12,16."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = HERE.parent / "generate.py"


def main() -> None:
    subprocess.run(
        [sys.executable, str(GEN), "--out", str(HERE / "build"), "-D", "8,12,16"],
        check=True,
    )


if __name__ == "__main__":
    main()
