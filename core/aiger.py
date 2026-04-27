"""Minimal AIGER ASCII (.aag) reader/writer for combinational circuits.

Skolem-function bundles are encoded as one multi-output AIG: inputs
named `u<id>` for each universal, outputs named `e<id>` for each
existential. See https://fmv.jku.at/aiger/FORMAT.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.formula import Formula
from core.semantics import Skolem


@dataclass(frozen=True)
class Aag:
    """Parsed combinational AIGER (no latches)."""

    max_var: int
    inputs: list[int]  # literals (even)
    outputs: list[int]  # literals
    gates: list[tuple[int, int, int]]  # (lhs, rhs0, rhs1), lhs even
    in_names: dict[int, str]  # input index -> name
    out_names: dict[int, str]  # output index -> name

    def input_by_name(self, name: str) -> int | None:
        for i, n in self.in_names.items():
            if n == name:
                return self.inputs[i]
        return None

    def output_by_name(self, name: str) -> int | None:
        for i, n in self.out_names.items():
            if n == name:
                return self.outputs[i]
        return None

    def cone_inputs(self, out_lit: int) -> set[int]:
        """Input literals reachable from `out_lit` through AND gates."""
        gate_map = {g: (a, b) for (g, a, b) in self.gates}
        in_set = set(self.inputs)
        seen: set[int] = set()
        result: set[int] = set()
        stack = [out_lit]
        while stack:
            lit = stack.pop()
            v = lit & ~1
            if v in seen or v == 0:
                continue
            seen.add(v)
            if v in in_set:
                result.add(v)
            elif v in gate_map:
                a, b = gate_map[v]
                stack += [a, b]
        return result


def parse_aag(text: str) -> Aag:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    hdr = lines[0].split()
    if hdr[0] != "aag" or len(hdr) != 6:
        raise ValueError(f"bad AIGER header: {lines[0]!r}")
    m, i, ll, o, a = (int(x) for x in hdr[1:])
    if ll != 0:
        raise ValueError("latches not supported")
    pos = 1
    inputs = [int(lines[pos + k]) for k in range(i)]
    pos += i
    outputs = [int(lines[pos + k]) for k in range(o)]
    pos += o
    gates: list[tuple[int, int, int]] = []
    for k in range(a):
        g, r0, r1 = (int(t) for t in lines[pos + k].split())
        gates.append((g, r0, r1))
    pos += a
    in_names: dict[int, str] = {}
    out_names: dict[int, str] = {}
    for ln in lines[pos:]:
        if ln.startswith("i"):
            idx, name = ln[1:].split(" ", 1)
            in_names[int(idx)] = name
        elif ln.startswith("o"):
            idx, name = ln[1:].split(" ", 1)
            out_names[int(idx)] = name
        elif ln.startswith("c"):
            break
    return Aag(
        max_var=m,
        inputs=inputs,
        outputs=outputs,
        gates=gates,
        in_names=in_names,
        out_names=out_names,
    )


def load_aag(path: str | Path) -> Aag:
    return parse_aag(Path(path).read_text())


@dataclass
class _Aig:
    n_inputs: int
    gates: list[tuple[int, int, int]] = field(default_factory=list)
    outputs: list[int] = field(default_factory=list)
    in_names: dict[int, str] = field(default_factory=dict)
    out_names: dict[int, str] = field(default_factory=dict)

    @property
    def max_var(self) -> int:
        return self.n_inputs + len(self.gates)

    def lit_input(self, i: int) -> int:
        return 2 * (i + 1)

    def mk_and(self, a: int, b: int) -> int:
        v = self.max_var + 1
        self.gates.append((2 * v, a, b))
        return 2 * v

    @staticmethod
    def neg(lit: int) -> int:
        return lit ^ 1

    def mk_or(self, a: int, b: int) -> int:
        return self.neg(self.mk_and(self.neg(a), self.neg(b)))

    def mk_ite(self, c: int, t: int, e: int) -> int:
        return self.mk_or(self.mk_and(c, t), self.mk_and(self.neg(c), e))

    def dumps(self) -> str:
        m, i, o, a = self.max_var, self.n_inputs, len(self.outputs), len(self.gates)
        lines = [f"aag {m} {i} 0 {o} {a}"]
        lines += [str(self.lit_input(k)) for k in range(i)]
        lines += [str(x) for x in self.outputs]
        lines += [f"{g} {a0} {a1}" for (g, a0, a1) in self.gates]
        for k, name in sorted(self.in_names.items()):
            lines.append(f"i{k} {name}")
        for k, name in sorted(self.out_names.items()):
            lines.append(f"o{k} {name}")
        return "\n".join(lines) + "\n"


def skolem_to_aag(f: Formula, sk: Skolem) -> str:
    """One combinational AIG: inputs = all universals; one output per existential."""
    us = list(f.universals)
    aig = _Aig(n_inputs=len(us))
    u_lit = {u: aig.lit_input(i) for i, u in enumerate(us)}
    for i, u in enumerate(us):
        aig.in_names[i] = f"u{u}"
    for oi, y in enumerate(sorted(sk)):
        deps = sorted(f.dependencies[y])
        out = _shannon(aig, sk[y], [u_lit[d] for d in deps])
        aig.outputs.append(out)
        aig.out_names[oi] = f"e{y}"
    return aig.dumps()


def _shannon(aig: _Aig, tbl: dict[tuple[bool, ...], bool], inputs: list[int]) -> int:
    def rec(prefix: tuple[bool, ...]) -> int:
        if len(prefix) == len(inputs):
            return 1 if tbl[prefix] else 0
        sel = inputs[len(prefix)]
        return aig.mk_ite(sel, rec(prefix + (True,)), rec(prefix + (False,)))

    return rec(())
