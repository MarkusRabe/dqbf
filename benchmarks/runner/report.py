"""Summarize a results JSONL into a per-family table."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def load_jsonl(path: str | Path) -> list[dict]:
    return [json.loads(ln) for ln in Path(path).read_text().splitlines() if ln.strip()]


def summarize(results: list[dict], group_by: str = "family") -> str:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        groups[r.get(group_by, "")].append(r)
    cols = ["group", "n", "ok", "wrong", "unknown", "timeout", "error", "med_wall_s"]
    rows = []
    for g, rs in sorted(groups.items()):
        n = len(rs)
        by: dict[str, int] = defaultdict(int)
        for r in rs:
            by[r["status"]] += 1
        walls = sorted(r["wall_s"] for r in rs)
        med = walls[n // 2] if walls else 0.0
        rows.append([g, n, by["ok"], by["wrong"], by["unknown"], by["timeout"], by["error"], med])
    widths = [max(len(str(row[i])) for row in [cols, *rows]) for i in range(len(cols))]
    lines = [
        "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(cols)),
        "  ".join("-" * w for w in widths),
    ]
    for row in rows:
        lines.append("  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)))
    return "\n".join(lines)
