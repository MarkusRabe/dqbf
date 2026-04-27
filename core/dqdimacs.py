"""DQDIMACS reader / writer.

Format (see docs/references/dqdimacs.md):
  c <comment>
  p cnf <vars> <clauses>
  a <u1> ... 0             universal block
  e <e1> ... 0             existentials depending on ALL preceding universals
  d <y> <u1> ... 0         existential y with explicit dependency set
  <l1> ... 0               clause
"""

from __future__ import annotations

import gzip
from collections.abc import Iterable
from pathlib import Path
from typing import TextIO

from core.formula import Clause, Formula


class ParseError(ValueError):
    pass


def parse(text: str) -> Formula:
    return _parse_lines(text.splitlines())


def load(path: str | Path) -> Formula:
    p = Path(path)
    if p.suffix == ".gz":
        with gzip.open(p, "rt") as f:
            return _parse_lines(f)
    return _parse_lines(p.read_text().splitlines())


def _parse_lines(lines: Iterable[str]) -> Formula:
    n_vars = 0
    n_clauses_declared = 0
    universals: list[int] = []
    deps: dict[int, frozenset[int]] = {}
    clauses: list[Clause] = []
    comments: list[str] = []
    seen_header = False

    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("c"):
            comments.append(line[1:].lstrip())
            continue
        toks = line.split()
        head = toks[0]
        if head == "p":
            if seen_header:
                raise ParseError(f"line {lineno}: duplicate header")
            if len(toks) != 4 or toks[1] != "cnf":
                raise ParseError(f"line {lineno}: bad header {line!r}")
            n_vars = int(toks[2])
            n_clauses_declared = int(toks[3])
            seen_header = True
            continue
        if not seen_header:
            raise ParseError(f"line {lineno}: data before 'p cnf' header")
        nums = [int(t) for t in toks[1:]] if head in ("a", "e", "d") else [int(t) for t in toks]
        if nums[-1] != 0:
            raise ParseError(f"line {lineno}: not 0-terminated")
        body = nums[:-1]
        if head == "a":
            universals.extend(body)
        elif head == "e":
            cur = frozenset(universals)
            for y in body:
                deps[y] = cur
        elif head == "d":
            if not body:
                raise ParseError(f"line {lineno}: empty 'd' line")
            y, *ds = body
            deps[y] = frozenset(ds)
        else:
            clauses.append(frozenset(nums[:-1]))

    _ = n_clauses_declared
    return Formula(
        n_vars=n_vars,
        universals=tuple(universals),
        dependencies=deps,
        clauses=tuple(clauses),
        comments=tuple(comments),
    )


def dump(f: Formula, out: TextIO) -> None:
    for c in f.comments:
        out.write(f"c {c}\n")
    out.write(f"p cnf {f.n_vars} {len(f.clauses)}\n")
    if f.universals:
        out.write("a " + " ".join(str(u) for u in f.universals) + " 0\n")
    for y in sorted(f.dependencies):
        ds = sorted(f.dependencies[y])
        out.write("d " + " ".join(str(v) for v in [y, *ds]) + " 0\n")
    for clause in f.clauses:
        out.write(" ".join(str(lit) for lit in sorted(clause, key=lambda x: (abs(x), x))) + " 0\n")


def dumps(f: Formula) -> str:
    import io

    buf = io.StringIO()
    dump(f, buf)
    return buf.getvalue()
