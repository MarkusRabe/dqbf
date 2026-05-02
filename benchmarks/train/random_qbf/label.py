"""Label generated instances with caqe (ground truth) and rewrite manifest.json."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
CAQE = HERE.parents[2] / "third_party/caqe/target/release/caqe"


def main() -> None:
    inst = HERE / "instances"
    m = json.loads((inst / "manifest.json").read_text())
    counts: dict[str, dict[str, int]] = {}
    for e in m:
        rc = subprocess.run([str(CAQE), str(inst / e["path"])], capture_output=True).returncode
        e["expected"] = {10: "sat", 20: "unsat"}.get(rc, "unknown")
        tag = e["tags"][1]
        counts.setdefault(tag, {"sat": 0, "unsat": 0, "unknown": 0})
        counts[tag][e["expected"]] += 1
    (inst / "manifest.json").write_text(json.dumps(m, indent=2))
    for k, v in counts.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
