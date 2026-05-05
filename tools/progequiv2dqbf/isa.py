"""Toy ISA for program-equivalence benchmarks.

A deliberately tiny register machine so that small instances fit
inside the brute-force `core.semantics` budget. Programs are static
instruction lists (Harvard architecture — code is not in `mem`).

Registers: r0..r{R-1}, each W bits.
Memory:    2^A cells, each W bits.
PC:        log2(len(prog)) bits, saturates at HALT.

Ops (one per source line, `#` comments allowed):
    MOV   rd imm        rd ← imm
    LOAD  rd ra         rd ← mem[ra]
    STORE ra rs         mem[ra] ← rs
    ADD   rd ra rb      rd ← (ra + rb) mod 2^W
    XOR   rd ra rb      rd ← ra ⊕ rb
    BEQ   ra rb tgt     if ra == rb: pc ← tgt
    HALT
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Instr:
    op: str
    args: tuple[int, ...]


@dataclass(frozen=True)
class Program:
    name: str
    instrs: tuple[Instr, ...]

    def __len__(self) -> int:
        return len(self.instrs)


OPS: dict[str, int] = {
    "MOV": 2,
    "LOAD": 2,
    "STORE": 2,
    "ADD": 3,
    "XOR": 3,
    "BEQ": 3,
    "HALT": 0,
}


def _arg(tok: str) -> int:
    return int(tok[1:]) if tok.startswith("r") else int(tok)


def parse(text: str, name: str = "<anon>") -> Program:
    instrs: list[Instr] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        op = parts[0].upper()
        if op not in OPS:
            raise ValueError(f"{name}: unknown op {op!r}")
        if len(parts) - 1 != OPS[op]:
            raise ValueError(f"{name}: {op} expects {OPS[op]} args, got {len(parts) - 1}")
        instrs.append(Instr(op, tuple(_arg(t) for t in parts[1:])))
    if not instrs or instrs[-1].op != "HALT":
        raise ValueError(f"{name}: program must end with HALT")
    return Program(name, tuple(instrs))


def load(path: str | Path) -> Program:
    p = Path(path)
    return parse(p.read_text(), name=p.stem)
