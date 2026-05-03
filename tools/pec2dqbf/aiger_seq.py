"""Minimal sequential-AIGER (.aag) reader.

`core/aiger.py` is combinational-only; BMC needs latches. This reader is
intentionally tiny: header, inputs, latches (lit + next + optional
reset), outputs, AND gates, and the symbol table. No bad/constraint/
fairness sections (AIGER 1.9 extensions) — first output is treated as
the "bad" signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Latch:
    lit: int  # current-state literal (even)
    next: int  # next-state function literal
    reset: int = 0  # 0, 1, or lit (= uninit)


@dataclass(frozen=True)
class SeqAig:
    max_var: int
    inputs: list[int]
    latches: list[Latch]
    outputs: list[int]
    gates: list[tuple[int, int, int]]
    symbols: dict[str, str] = field(default_factory=dict)

    @property
    def bad(self) -> int:
        return self.outputs[0] if self.outputs else 0

    def gate_map(self) -> dict[int, tuple[int, int]]:
        return {g: (a, b) for g, a, b in self.gates}

    def cone_inputs(self, lit: int, stop_at: set[int]) -> set[int]:
        """Even literals from `stop_at` reachable from `lit` through gates."""
        gm = self.gate_map()
        seen: set[int] = set()
        out: set[int] = set()
        stack = [lit]
        while stack:
            v = stack.pop() & ~1
            if v in seen or v == 0:
                continue
            seen.add(v)
            if v in stop_at:
                out.add(v)
            elif v in gm:
                a, b = gm[v]
                stack += [a, b]
        return out


def parse_seq_aag(text: str) -> SeqAig:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("empty AIGER")
    hdr = lines[0].split()
    if hdr[0] != "aag" or len(hdr) < 6:
        raise ValueError(f"bad AIGER header: {lines[0]!r}")
    m, ni, nl, no, na = (int(x) for x in hdr[1:6])
    pos = 1
    inputs = [int(lines[pos + k]) for k in range(ni)]
    pos += ni
    latches: list[Latch] = []
    for k in range(nl):
        toks = lines[pos + k].split()
        latches.append(Latch(int(toks[0]), int(toks[1]), int(toks[2]) if len(toks) > 2 else 0))
    pos += nl
    outputs = [int(lines[pos + k]) for k in range(no)]
    pos += no
    gates: list[tuple[int, int, int]] = []
    for k in range(na):
        g, a, b = (int(t) for t in lines[pos + k].split())
        gates.append((g, a, b))
    pos += na
    syms: dict[str, str] = {}
    for ln in lines[pos:]:
        if ln[0] in "iloc" and " " in ln:
            key, name = ln.split(" ", 1)
            syms[key] = name
        elif ln == "c":
            break
    return SeqAig(m, inputs, latches, outputs, gates, syms)


def load_seq_aag(path: str | Path) -> SeqAig:
    return parse_seq_aag(Path(path).read_text())
