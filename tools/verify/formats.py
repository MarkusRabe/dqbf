"""Self-contained data-format readers for the verifier.

Deliberately duplicates a subset of core/{formula,dqdimacs,aiger,
proof_trace}.py so that `tools/verify/` has **no imports outside
itself** (stdlib aside). The types here are read-only and minimal —
just what the checkers need.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path

# --- DQBF formula ---------------------------------------------------------

Clause = frozenset[int]


@dataclass(frozen=True)
class Formula:
    n_vars: int
    universals: tuple[int, ...]
    dependencies: dict[int, frozenset[int]]
    clauses: tuple[Clause, ...]

    def is_universal(self, v: int) -> bool:
        return v in self.universals

    def is_existential(self, v: int) -> bool:
        return v in self.dependencies

    def with_existential(self, y: int, deps: frozenset[int]) -> Formula:
        d = dict(self.dependencies)
        d[y] = deps
        return Formula(max(self.n_vars, y), self.universals, d, self.clauses)


def load_dqdimacs(path: str | Path) -> Formula:
    p = Path(path)
    text = gzip.open(p, "rt").read() if p.suffix == ".gz" else p.read_text()
    return parse_dqdimacs(text)


def parse_dqdimacs(text: str) -> Formula:
    n_vars = 0
    us: list[int] = []
    deps: dict[int, frozenset[int]] = {}
    cls: list[Clause] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("c"):
            continue
        toks = line.split()
        if toks[0] == "p":
            n_vars = int(toks[2])
            continue
        nums = [int(t) for t in (toks[1:] if toks[0] in ("a", "e", "d") else toks)]
        body = nums[:-1]
        if toks[0] == "a":
            us.extend(body)
        elif toks[0] == "e":
            cur = frozenset(us)
            for y in body:
                deps[y] = cur
        elif toks[0] == "d":
            deps[body[0]] = frozenset(body[1:])
        else:
            cls.append(frozenset(nums[:-1]))
    return Formula(n_vars, tuple(us), deps, tuple(cls))


# --- AIGER ASCII (.aag) ---------------------------------------------------


@dataclass(frozen=True)
class Aag:
    inputs: list[int]
    outputs: list[int]
    gates: list[tuple[int, int, int]]
    in_names: dict[int, str]
    out_names: dict[int, str]

    def output_by_name(self, name: str) -> int | None:
        for i, n in self.out_names.items():
            if n == name:
                return self.outputs[i]
        return None

    def cone_inputs(self, out_lit: int) -> set[int]:
        gate_map = {g: (a, b) for (g, a, b) in self.gates}
        in_set = set(self.inputs)
        seen: set[int] = set()
        result: set[int] = set()
        stack = [out_lit]
        while stack:
            v = stack.pop() & ~1
            if v in seen or v == 0:
                continue
            seen.add(v)
            if v in in_set:
                result.add(v)
            elif v in gate_map:
                a, b = gate_map[v]
                stack += [a, b]
        return result


def load_aag(path: str | Path) -> Aag:
    return parse_aag(Path(path).read_text())


def parse_aag(text: str) -> Aag:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("empty AIGER")
    hdr = lines[0].split()
    if hdr[0] != "aag" or len(hdr) != 6 or hdr[3] != "0":
        raise ValueError(f"bad/non-combinational AIGER header: {lines[0]!r}")
    m, ni, _nl, no, na = (int(x) for x in hdr[1:])
    max_lit = 2 * m + 1
    pos = 1
    inputs = [int(lines[pos + k]) for k in range(ni)]
    pos += ni
    outputs = [int(lines[pos + k]) for k in range(no)]
    pos += no
    gates: list[tuple[int, int, int]] = []
    for k in range(na):
        g, a, b = (int(t) for t in lines[pos + k].split())
        gates.append((g, a, b))
    pos += na
    in_names: dict[int, str] = {}
    out_names: dict[int, str] = {}
    for ln in lines[pos:]:
        if ln[0] == "i":
            idx, name = ln[1:].split(" ", 1)
            if not (0 <= int(idx) < ni):
                raise ValueError(f"input symbol index out of range: {ln!r}")
            in_names[int(idx)] = name
        elif ln[0] == "o":
            idx, name = ln[1:].split(" ", 1)
            if not (0 <= int(idx) < no):
                raise ValueError(f"output symbol index out of range: {ln!r}")
            out_names[int(idx)] = name
        elif ln[0] == "c":
            break

    in_set = set(inputs)
    defined = in_set | {g for g, _, _ in gates} | {0}
    for lit in inputs:
        if lit <= 0 or lit & 1 or lit > max_lit:
            raise ValueError(f"bad input literal {lit}")
    for g, a, b in gates:
        if g <= 0 or g & 1 or g > max_lit or g in in_set:
            raise ValueError(f"bad gate lhs {g}")
        if (a & ~1) not in defined or (b & ~1) not in defined:
            raise ValueError(f"gate {g}: operand references undefined literal")
    for lit in outputs:
        if (lit & ~1) not in defined:
            raise ValueError(f"output literal {lit} undefined")
    return Aag(inputs, outputs, gates, in_names, out_names)


# --- Fork-resolution proof trace (.frp) -----------------------------------


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


def load_proof(path: str | Path) -> Proof:
    raw = json.loads(Path(path).read_text())
    return Proof(
        steps=[
            Step(
                clause=tuple(s["clause"]),
                rule=s["rule"],
                premises=tuple(s.get("premises") or ()),
                pivot=s.get("pivot"),
                part=tuple(s["part"]) if s.get("part") is not None else None,
                c3=tuple(s["c3"]) if s.get("c3") is not None else None,
                fresh=s.get("fresh"),
            )
            for s in raw
        ]
    )
