"""Minimal AIGER ASCII (.aag) writer for combinational Skolem circuits.

Just enough to emit one circuit per existential variable as a multi-
output AIG: inputs are the dependency-set bits, outputs are the
existential bits, gates are 2-input ANDs with optional inversion encoded
in the LSB. See https://fmv.jku.at/aiger/FORMAT.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.formula import Formula
from core.semantics import Skolem


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
        lines += [f"{g} {l} {r}" for (g, l, r) in self.gates]
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
