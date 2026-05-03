"""Compose DQBF formulas: variable-disjoint conjunction.

Used by `benchmarks/train/conjunction/` to test whether solvers detect
that a formula is a conjunction of independent connected components.
"""

from __future__ import annotations

from collections.abc import Sequence

from core.formula import Clause, Formula


def shift(f: Formula, offset: int) -> Formula:
    """Relabel every variable v → v + offset."""
    if offset < 0:
        raise ValueError("offset must be non-negative")
    if offset == 0:
        return f

    def sl(lit: int) -> int:
        return lit + offset if lit > 0 else lit - offset

    deps = {y + offset: frozenset(u + offset for u in d) for y, d in f.dependencies.items()}
    return Formula(
        n_vars=f.n_vars + offset,
        universals=tuple(u + offset for u in f.universals),
        dependencies=deps,
        clauses=tuple(frozenset(sl(lit) for lit in c) for c in f.clauses),
        comments=f.comments,
    )


def conjoin(formulas: Sequence[Formula], comments: Sequence[str] = ()) -> Formula:
    """Variable-disjoint conjunction.

    Each component's variables are shifted into a fresh range so no two
    components share a literal. The result is SAT iff every component is
    SAT (Skolem functions concatenate component-wise).
    """
    if not formulas:
        raise ValueError("conjoin requires at least one formula")
    universals: list[int] = []
    deps: dict[int, frozenset[int]] = {}
    clauses: list[Clause] = []
    offset = 0
    for f in formulas:
        g = shift(f, offset)
        universals.extend(g.universals)
        deps.update(g.dependencies)
        clauses.extend(g.clauses)
        offset += f.n_vars
    return Formula(
        n_vars=offset,
        universals=tuple(universals),
        dependencies=deps,
        clauses=tuple(clauses),
        comments=tuple(comments),
    )
