"""DQBF formula IR shared by provers, encoders, and the verifier.

A literal is a non-zero int: +v for variable v, -v for its negation.
A clause is a frozenset of literals.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field

Lit = int
Clause = frozenset[int]


def var(lit: Lit) -> int:
    return abs(lit)


def neg(lit: Lit) -> Lit:
    return -lit


@dataclass(frozen=True)
class Formula:
    """A DQBF in prenex CNF.

    `universals` is the ordered tuple of universal variable IDs.
    `dependencies[y]` is the dependency set of existential y (subset of
    `universals`). Every variable in 1..n_vars is either universal or
    existential.
    """

    n_vars: int
    universals: tuple[int, ...]
    dependencies: dict[int, frozenset[int]]
    clauses: tuple[Clause, ...]
    comments: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        us = set(self.universals)
        for y, deps in self.dependencies.items():
            if y in us:
                raise ValueError(f"variable {y} is both universal and existential")
            if not deps <= us:
                bad = deps - us
                raise ValueError(f"existential {y} depends on non-universals {sorted(bad)}")
        for c in self.clauses:
            for lit in c:
                if lit == 0 or var(lit) > self.n_vars:
                    raise ValueError(f"bad literal {lit} (n_vars={self.n_vars})")

    @property
    def existentials(self) -> tuple[int, ...]:
        return tuple(sorted(self.dependencies))

    def is_universal(self, v: int) -> bool:
        return v in self.universals

    def is_existential(self, v: int) -> bool:
        return v in self.dependencies

    def dep(self, v: int) -> frozenset[int]:
        """Dependency set: deps[y] for existential y, {x} for universal x."""
        if v in self.dependencies:
            return self.dependencies[v]
        return frozenset({v})

    def clause_dep(self, clause: Iterable[Lit]) -> frozenset[int]:
        """Union of dep(v) over all literals in the clause."""
        out: set[int] = set()
        for lit in clause:
            out |= self.dep(var(lit))
        return frozenset(out)

    def with_clauses(self, clauses: Iterable[Clause]) -> Formula:
        return Formula(
            n_vars=self.n_vars,
            universals=self.universals,
            dependencies=dict(self.dependencies),
            clauses=tuple(clauses),
            comments=self.comments,
        )

    def add_existential(self, y: int, deps: frozenset[int]) -> Formula:
        """Return a copy with one fresh existential variable appended."""
        if y <= self.n_vars:
            raise ValueError(f"variable {y} not fresh (n_vars={self.n_vars})")
        new_deps = dict(self.dependencies)
        new_deps[y] = deps
        return Formula(
            n_vars=y,
            universals=self.universals,
            dependencies=new_deps,
            clauses=self.clauses,
            comments=self.comments,
        )

    def __iter__(self) -> Iterator[Clause]:
        return iter(self.clauses)

    def __len__(self) -> int:
        return len(self.clauses)


def make_formula(
    universals: Iterable[int],
    dependencies: Mapping[int, Iterable[int]],
    clauses: Iterable[Iterable[Lit]],
    comments: Iterable[str] = (),
) -> Formula:
    """Convenience constructor that freezes inputs and infers n_vars."""
    us = tuple(universals)
    deps = {y: frozenset(d) for y, d in dependencies.items()}
    cls = tuple(frozenset(c) for c in clauses)
    n = 0
    for v in us:
        n = max(n, v)
    for y in deps:
        n = max(n, y)
    for c in cls:
        for lit in c:
            n = max(n, var(lit))
    return Formula(
        n_vars=n, universals=us, dependencies=deps, clauses=cls, comments=tuple(comments)
    )
