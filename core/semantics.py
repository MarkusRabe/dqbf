"""Brute-force DQBF truth evaluation for tiny instances.

Enumerates every Skolem-function tuple and every universal assignment.
Exponential in |universals| and double-exponential in max dependency-set
size — use only for instances with a handful of variables, as a
ground-truth oracle for testing the prover.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable

from core.formula import Clause, Formula, var

Assignment = dict[int, bool]
Skolem = dict[int, dict[tuple[bool, ...], bool]]


def eval_clause(clause: Clause, a: Assignment) -> bool:
    return any((a[var(lit)] if lit > 0 else not a[var(lit)]) for lit in clause)


def eval_matrix(clauses: Iterable[Clause], a: Assignment) -> bool:
    return all(eval_clause(c, a) for c in clauses)


def _all_universal_assignments(f: Formula) -> Iterable[Assignment]:
    us = f.universals
    for bits in itertools.product((False, True), repeat=len(us)):
        yield dict(zip(us, bits, strict=True))


def _apply_skolem(f: Formula, sk: Skolem, ua: Assignment) -> Assignment:
    a = dict(ua)
    for y, deps in f.dependencies.items():
        key = tuple(ua[u] for u in sorted(deps))
        a[y] = sk[y][key]
    return a


def _all_skolem_tuples(f: Formula) -> Iterable[Skolem]:
    exs = sorted(f.dependencies)
    dep_lists = {y: sorted(f.dependencies[y]) for y in exs}
    domains = {y: list(itertools.product((False, True), repeat=len(dep_lists[y]))) for y in exs}
    spaces = []
    for y in exs:
        funcs = []
        for outs in itertools.product((False, True), repeat=len(domains[y])):
            funcs.append(dict(zip(domains[y], outs, strict=True)))
        spaces.append(funcs)
    for choice in itertools.product(*spaces):
        yield dict(zip(exs, choice, strict=True))


def is_true(f: Formula, budget: int = 200_000) -> bool | None:
    """True/False if decidable within `budget` Skolem candidates, else None."""
    count = 0
    for sk in _all_skolem_tuples(f):
        count += 1
        if count > budget:
            return None
        if all(
            eval_matrix(f.clauses, _apply_skolem(f, sk, ua)) for ua in _all_universal_assignments(f)
        ):
            return True
    return False


def find_skolem(f: Formula, budget: int = 200_000) -> Skolem | None:
    count = 0
    for sk in _all_skolem_tuples(f):
        count += 1
        if count > budget:
            return None
        if all(
            eval_matrix(f.clauses, _apply_skolem(f, sk, ua)) for ua in _all_universal_assignments(f)
        ):
            return sk
    return None
