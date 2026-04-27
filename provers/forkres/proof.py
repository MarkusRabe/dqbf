"""Fork-resolution refutation traces (`.frp`).

A proof is a list of steps; step i derives clause `clause` by `rule`
from earlier step indices `premises` (and, for FEx/SFEx, the partition
and fresh var). Replay checks each step independently.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from core.formula import Clause, Formula
from provers.forkres.rules import resolve, universal_reduce


@dataclass(frozen=True)
class Step:
    clause: tuple[int, ...]
    rule: str
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
        steps = []
        for s in raw:
            steps.append(
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
        p = Proof()
        p.steps = steps
        return p


def replay(f: Formula, proof: Proof) -> bool:
    """Check every step; return True iff all valid and ⊥ is derived."""
    g = f
    derived: list[Clause] = []
    for s in proof.steps:
        c = frozenset(s.clause)
        if s.rule == "axiom":
            if c not in g.clauses:
                return False
        elif s.rule == "res":
            if len(s.premises) != 2 or s.pivot is None:
                return False
            r = resolve(derived[s.premises[0]], derived[s.premises[1]], s.pivot)
            if r is None or universal_reduce(g, r) != c:
                return False
        elif s.rule == "ured":
            if len(s.premises) != 1:
                return False
            if universal_reduce(g, derived[s.premises[0]]) != c:
                return False
        elif s.rule in ("fex", "sfex"):
            if len(s.premises) != 1 or s.part is None or s.fresh is None:
                return False
            src = derived[s.premises[0]]
            part = frozenset(s.part)
            if not part <= src:
                return False
            c3 = frozenset(s.c3 or ())
            c1, c2 = part, src - part
            left = c3 | c1 | {s.fresh}
            right = c3 | c2 | {-s.fresh}
            if c not in (left, right):
                return False
            if s.fresh > g.n_vars:
                d1, d2 = g.clause_dep(c1), g.clause_dep(c2)
                drop = frozenset(abs(lit) for lit in c3) if s.rule == "sfex" else frozenset()
                if s.rule == "sfex" and any(not g.is_universal(abs(lit)) for lit in c3):
                    return False
                g = g.add_existential(s.fresh, (d1 & d2) - drop)
            elif not g.is_existential(s.fresh):
                return False
        else:
            return False
        derived.append(c)
    return frozenset() in derived


def save(path: str | Path, proof: Proof) -> None:
    Path(path).write_text(proof.dumps())


def load(path: str | Path) -> Proof:
    return Proof.loads(Path(path).read_text())
