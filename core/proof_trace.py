"""Fork-resolution proof-trace format (`.frp`).

Pure data: the `Step`/`Proof` types and JSON (de)serialization. No rule
logic here — provers emit this, `tools/verify/unsat.py` checks it
without importing anything from `provers/`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Step:
    clause: tuple[int, ...]
    rule: str  # "axiom" | "res" | "ured" | "fex" | "sfex"
    premises: tuple[int, ...] = ()
    pivot: int | None = None
    part: tuple[int, ...] | None = None
    c3: tuple[int, ...] | None = None
    fresh: int | None = None


@dataclass
class Proof:
    steps: list[Step] = field(default_factory=list)

    def add(self, **kw) -> int:
        self.steps.append(Step(**kw))
        return len(self.steps) - 1

    def is_refutation(self) -> bool:
        return any(len(s.clause) == 0 for s in self.steps)

    def dumps(self) -> str:
        return json.dumps([asdict(s) for s in self.steps])

    @staticmethod
    def loads(text: str) -> Proof:
        raw = json.loads(text)
        p = Proof()
        for s in raw:
            p.steps.append(
                Step(
                    clause=tuple(s["clause"]),
                    rule=s["rule"],
                    premises=tuple(s.get("premises") or ()),
                    pivot=s.get("pivot"),
                    part=tuple(s["part"]) if s.get("part") is not None else None,
                    c3=tuple(s["c3"]) if s.get("c3") is not None else None,
                    fresh=s.get("fresh"),
                )
            )
        return p


def save(path: str | Path, proof: Proof) -> None:
    Path(path).write_text(proof.dumps())


def load(path: str | Path) -> Proof:
    return Proof.loads(Path(path).read_text())
