"""Naive fork-resolution refutation search.

Correctness-only: saturate Res+∀Red, then apply FEx on information-fork
clauses and re-saturate, up to a step budget. Returns UNSAT when the
empty clause is derived; SAT when saturation is reached with no fork
clauses left; otherwise UNKNOWN.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from core.formula import Clause, Formula
from provers.forkres.rules import (
    find_information_fork,
    fork_extend,
    is_tautology,
    resolvents,
    universal_reduce,
)


class Result(Enum):
    SAT = 10
    UNSAT = 20
    UNKNOWN = 0


@dataclass
class Trace:
    steps: list[str] = field(default_factory=list)

    def log(self, msg: str) -> None:
        self.steps.append(msg)


@dataclass
class SearchConfig:
    max_clauses: int = 5_000
    max_forks: int = 32
    timeout_s: float = 1.0


def _saturate(f: Formula, clauses: set[Clause], cfg: SearchConfig, deadline: float) -> set[Clause]:
    """Res+∀Red to fixpoint or budget."""
    todo = list(clauses)
    db = set(clauses)
    while todo:
        if time.monotonic() > deadline or len(db) > cfg.max_clauses:
            break
        c = todo.pop()
        for d in list(db):
            if d is c:
                continue
            for r in resolvents(f, c, d):
                if r not in db:
                    db.add(r)
                    todo.append(r)
                    if not r:
                        return db
    return db


def solve(f: Formula, cfg: SearchConfig | None = None) -> tuple[Result, Trace]:
    cfg = cfg or SearchConfig()
    deadline = time.monotonic() + cfg.timeout_s
    trace = Trace()

    clauses: set[Clause] = set()
    for c in f.clauses:
        rc = universal_reduce(f, c)
        if not is_tautology(rc):
            clauses.add(rc)
    if frozenset() in clauses:
        trace.log("empty clause in input after ∀-reduction")
        return Result.UNSAT, trace

    g = f
    forks = 0
    while True:
        clauses = _saturate(g, clauses, cfg, deadline)
        if frozenset() in clauses:
            trace.log(f"derived ⊥ after {len(clauses)} clauses, {forks} forks")
            return Result.UNSAT, trace
        if time.monotonic() > deadline or len(clauses) > cfg.max_clauses:
            trace.log(f"budget exhausted: {len(clauses)} clauses, {forks} forks")
            return Result.UNKNOWN, trace
        forked_any = False
        for c in sorted(clauses, key=len):
            pair = find_information_fork(g, c)
            if pair is None:
                continue
            a, _b = pair
            part = frozenset(lit for lit in c if abs(lit) == a or g.dep(abs(lit)) <= g.dep(a))
            fr = fork_extend(g, c, part)
            g = fr.formula
            clauses.discard(c)
            clauses.add(universal_reduce(g, fr.left))
            clauses.add(universal_reduce(g, fr.right))
            forks += 1
            forked_any = True
            trace.log(f"FEx on {sorted(c)} → fresh x{fr.fresh}")
            break
        if not forked_any:
            trace.log(f"saturated, no forks: {len(clauses)} clauses")
            return Result.SAT, trace
        if forks >= cfg.max_forks:
            trace.log(f"fork budget exhausted ({forks})")
            return Result.UNKNOWN, trace
