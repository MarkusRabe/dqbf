"""Naive fork-resolution refutation search.

Correctness-only: saturate Res+∀Red, then apply FEx on information-fork
clauses and re-saturate, up to a step budget. Returns UNSAT (with a
checkable Proof) when the empty clause is derived; SAT (with a Skolem
certificate found by brute force) when saturation is reached with no
fork clauses left; otherwise UNKNOWN.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from core.formula import Clause, Formula
from core.semantics import Skolem, find_skolem
from provers.forkres.proof import Proof
from provers.forkres.rules import (
    find_information_fork,
    fork_extend,
    is_tautology,
    resolve,
    strong_fork_extend,
    universal_reduce,
)


class Result(Enum):
    SAT = 10
    UNSAT = 20
    UNKNOWN = 0


@dataclass
class SearchConfig:
    max_clauses: int = 5_000
    max_forks: int = 32
    timeout_s: float = 1.0
    extract_cert: bool = True


@dataclass
class SearchOutput:
    result: Result
    proof: Proof | None = None
    skolem: Skolem | None = None
    log: list[str] = field(default_factory=list)


def solve(f: Formula, cfg: SearchConfig | None = None) -> SearchOutput:
    cfg = cfg or SearchConfig()
    deadline = time.monotonic() + cfg.timeout_s
    out = SearchOutput(result=Result.UNKNOWN)
    proof = Proof()

    idx: dict[Clause, int] = {}

    def admit(c: Clause, **kw) -> int:
        if c in idx:
            return idx[c]
        i = proof.add(clause=tuple(sorted(c)), **kw)
        idx[c] = i
        return i

    g = f
    clauses: set[Clause] = set()
    for c in g.clauses:
        if is_tautology(c):
            continue
        ai = admit(c, rule="axiom")
        rc = universal_reduce(g, c)
        if rc != c:
            admit(rc, rule="ured", premises=(ai,))
        clauses.add(rc)

    if frozenset() in clauses:
        out.result = Result.UNSAT
        out.proof = proof
        return out

    forks = 0
    while True:
        clauses, derived_empty = _saturate(g, clauses, idx, admit, cfg, deadline)
        if derived_empty:
            out.result = Result.UNSAT
            out.proof = proof
            out.log.append(f"derived ⊥ after {len(clauses)} clauses, {forks} forks")
            return out
        if time.monotonic() > deadline or len(clauses) > cfg.max_clauses:
            out.log.append(f"budget exhausted: {len(clauses)} clauses, {forks} forks")
            return out
        forked_any = False
        for c in sorted(clauses, key=lambda x: (len(x), tuple(sorted(x)))):
            pair = find_information_fork(g, c)
            if pair is None:
                continue
            a, _b = pair
            part = frozenset(lit for lit in c if abs(lit) == a or g.dep(abs(lit)) <= g.dep(a))
            d1, d2 = g.clause_dep(part), g.clause_dep(c - part)
            inter = d1 & d2
            src = idx[c]
            spart = tuple(sorted(part))
            if inter and (inter == d1 or inter == d2):
                u = min(inter)
                fr = strong_fork_extend(g, c, part, c3=frozenset({u}))
                rule, c3 = "sfex", (u,)
                out.log.append(f"SFEx on {sorted(c)} c3={{{u}}} → x{fr.fresh}")
            else:
                fr = fork_extend(g, c, part)
                rule, c3 = "fex", None
                out.log.append(f"FEx on {sorted(c)} → x{fr.fresh}")
            g = fr.formula
            admit(fr.left, rule=rule, premises=(src,), part=spart, c3=c3, fresh=fr.fresh)
            admit(fr.right, rule=rule, premises=(src,), part=spart, c3=c3, fresh=fr.fresh)
            clauses.discard(c)
            for nc in (fr.left, fr.right):
                rnc = universal_reduce(g, nc)
                if rnc != nc:
                    admit(rnc, rule="ured", premises=(idx[nc],))
                clauses.add(rnc)
            forks += 1
            forked_any = True
            break
        if not forked_any:
            out.result = Result.SAT
            out.log.append(f"saturated, no forks: {len(clauses)} clauses")
            if cfg.extract_cert:
                out.skolem = find_skolem(f)
            return out
        if forks >= cfg.max_forks:
            out.log.append(f"fork budget exhausted ({forks})")
            return out


def _saturate(
    g: Formula,
    clauses: set[Clause],
    idx: dict[Clause, int],
    admit,
    cfg: SearchConfig,
    deadline: float,
) -> tuple[set[Clause], bool]:
    todo = list(clauses)
    db = set(clauses)
    while todo:
        if time.monotonic() > deadline or len(db) > cfg.max_clauses:
            break
        c = todo.pop()
        for d in list(db):
            if d is c:
                continue
            for lit in c:
                if -lit not in d:
                    continue
                r = resolve(c, d, abs(lit))
                if r is None:
                    continue
                rr = universal_reduce(g, r)
                if rr in db:
                    continue
                admit(rr, rule="res", premises=(idx[c], idx[d]), pivot=abs(lit))
                db.add(rr)
                todo.append(rr)
                if not rr:
                    return db, True
    return db, False
