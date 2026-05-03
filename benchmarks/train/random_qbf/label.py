"""Label generated instances with caqe (ground truth) and rewrite manifest.json."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
CAQE = HERE.parents[2] / "third_party/caqe/target/release/caqe"


def main() -> None:
    base = HERE / "v1"
    for sub in sorted(base.iterdir()):
        mf = sub / "manifest.json"
        if not mf.exists():
            continue
        m = json.loads(mf.read_text())
        counts = {"sat": 0, "unsat": 0, "unknown": 0}
        for e in m:
            rc = subprocess.run([str(CAQE), str(sub / e["path"])], capture_output=True).returncode
            e["expected"] = {10: "sat", 20: "unsat"}.get(rc, "unknown")
            counts[e["expected"]] += 1
        mf.write_text(json.dumps(m, indent=2))
        print(f"{sub.name}: {counts}")


if __name__ == "__main__":
    main()
