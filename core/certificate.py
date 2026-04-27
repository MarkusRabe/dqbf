"""Skolem-function certificates.

Two on-disk forms:
- JSON truth-table (`.skolem.json`) — exact, works for any width, used by
  the verifier and tests.
- AIGER ASCII (`.aag`) — the interchange format; built from the truth
  table by Shannon expansion.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.formula import Formula
from core.semantics import Skolem


def skolem_to_json(f: Formula, sk: Skolem) -> str:
    out: dict[str, dict[str, object]] = {}
    for y, tbl in sk.items():
        deps = sorted(f.dependencies[y])
        out[str(y)] = {
            "deps": deps,
            "table": {"".join("1" if b else "0" for b in k): v for k, v in tbl.items()},
        }
    return json.dumps(out, indent=2, sort_keys=True)


def skolem_from_json(text: str) -> Skolem:
    raw = json.loads(text)
    sk: Skolem = {}
    for y_s, entry in raw.items():
        y = int(y_s)
        tbl: dict[tuple[bool, ...], bool] = {}
        for bits, v in entry["table"].items():
            tbl[tuple(c == "1" for c in bits)] = bool(v)
        sk[y] = tbl
    return sk


def save_skolem(path: str | Path, f: Formula, sk: Skolem) -> None:
    Path(path).write_text(skolem_to_json(f, sk))


def load_skolem(path: str | Path) -> Skolem:
    return skolem_from_json(Path(path).read_text())
