"""Program-pair equivalence → DQBF, with memory as a Skolem function.

The point of this encoding (vs. CBMC-style array unrolling) is that
each program's memory trace is a *single* existential function
`mem : 2^(m+A) → 2^W` over `(step, addr)`, declared once with
`dep(mem_b) = {t, a}`. The DQBF prefix expresses "there exists a
memory trace" directly; the matrix asserts the trace is consistent
with the ISA semantics. Instance size is O(|prog| · (m+A+W)),
independent of 2^A and of the bound K beyond `m = ⌈log₂ K⌉`.

Prefix shape (bounded-trace mode):

    universals    t[0..m), t'[0..m), a[0..A), a'[0..A)
    existentials  per program ∈ {P, Q}, per bit b:
                    mem_b(t, a),  mem'_b(t', a')      — same function
                    reg_{r,b}(t), reg'_{r,b}(t')      — same function
                    pc_b(t),      pc'_b(t')           — same function
                  Tseitin aux over the union deps as needed.

    matrix
      (consist)   t==t' ∧ a==a' → mem_b ↔ mem'_b
                  t==t'         → reg/pc ↔ reg'/pc'
      (input)     t==0 → memP_b(0,a) ↔ memQ_b(0,a)      [shared input]
      (init)      t==0 → reg=0 ∧ pc=0
      (step)      t'==t+1: per-PC instruction semantics
                    — mem frame: a' ≠ store_addr → mem'_b ↔ mem_b@{t,a'}
                    — store:     a' == store_addr → mem'_b ↔ reg_{rs,b}
                    — reg/pc update from the instruction at pc(t)
      (halt)      pc==HALT_IDX → pc'==HALT_IDX (saturate)
      (equiv)     both halted → output_reg_P == output_reg_Q

Semantics: SAT ⇒ the programs are observationally equivalent on every
W-bit memory image within K steps; UNSAT ⇒ some input distinguishes
them (or one fails to halt within K — see README caveat).

Inductive-coupling mode delegates to `tools.hwmc2dqbf_indinv.encode`
on the product machine; see `encode_coupling`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from core.formula import Formula, make_formula
from tools.hwmc2dqbf_indinv.encode import Transition, encode_indinv
from tools.progequiv2dqbf.isa import Program


@dataclass(frozen=True)
class Config:
    word_bits: int = 2
    addr_bits: int = 2
    n_regs: int = 4
    bound: int = 8
    out_reg: int = 0


# --- CNF builder helpers (mirrors tools.bmc2dqbf.encode) ------------------


@dataclass
class _Builder:
    universals: list[int]
    deps: dict[int, frozenset[int]]
    clauses: list[list[int]]
    nxt: int = 1

    def fu(self) -> int:
        v = self.nxt
        self.nxt += 1
        self.universals.append(v)
        return v

    def fe(self, d: frozenset[int]) -> int:
        v = self.nxt
        self.nxt += 1
        self.deps[v] = d
        return v

    def t_and(self, out: int, a: int, b: int) -> None:
        self.clauses.extend(([-out, a], [-out, b], [out, -a, -b]))

    def t_iff(self, out: int, a: int, b: int) -> None:
        self.clauses.extend(([-out, -a, b], [-out, a, -b], [out, a, b], [out, -a, -b]))

    def big_and(self, ins: list[int], d: frozenset[int]) -> int:
        if len(ins) == 1:
            return ins[0]
        out = self.fe(d)
        for x in ins:
            self.clauses.append([-out, x])
        self.clauses.append([out] + [-x for x in ins])
        return out

    def eq_const(self, bits: list[int], c: int, d: frozenset[int]) -> int:
        """Literal that is true iff `bits` == constant `c` (LSB first)."""
        lits = [bits[i] if (c >> i) & 1 else -bits[i] for i in range(len(bits))]
        return self.big_and(lits, d)

    def eq_vec(self, xs: list[int], ys: list[int], d: frozenset[int]) -> int:
        per = []
        for x, y in zip(xs, ys, strict=True):
            e = self.fe(d)
            self.t_iff(e, x, y)
            per.append(e)
        return self.big_and(per, d)

    def implies_iff(self, guard: int, xs: list[int], ys: list[int]) -> None:
        for x, y in zip(xs, ys, strict=True):
            self.clauses.extend(([-guard, -x, y], [-guard, x, -y]))

    def ripple_add(self, xs: list[int], ys: list[int], d: frozenset[int]) -> list[int]:
        out: list[int] = []
        carry: int | None = None
        for x, y in zip(xs, ys, strict=True):
            xy = self.fe(d)
            self.t_iff(xy, x, y)  # x ⊕ y
            if carry is None:
                out.append(xy)
                carry = self.fe(d)
                self.t_and(carry, x, y)
            else:
                s = self.fe(d)
                self.t_iff(s, xy, -carry)  # xy ⊕ carry == xy ↔ ¬carry
                out.append(s)
                g1 = self.fe(d)
                self.t_and(g1, x, y)
                g2 = self.fe(d)
                self.t_and(g2, xy, carry)
                c2 = self.fe(d)
                self.clauses.extend(([-c2, g1, g2], [c2, -g1], [c2, -g2]))
                carry = c2
        return out

    def increment(self, bits: list[int], d: frozenset[int]) -> tuple[list[int], int]:
        out: list[int] = []
        carry = self.fe(d)
        self.clauses.append([carry])
        for b in bits:
            s = self.fe(d)
            self.t_iff(s, b, -carry)
            out.append(s)
            c2 = self.fe(d)
            self.t_and(c2, b, carry)
            carry = c2
        return out, carry


# --- per-program trace ----------------------------------------------------


@dataclass
class _Trace:
    """One program's Skolem-function variables, in both index copies."""

    mem: list[int]  # mem_b(t, a)
    memp: list[int]  # mem_b(t', a')
    reg: list[list[int]]  # reg[r][b](t)
    regp: list[list[int]]
    pc: list[int]  # pc_b(t)
    pcp: list[int]
    halted: int  # pc(t) == HALT_IDX
    haltedp: int


def _alloc_trace(
    b: _Builder,
    cfg: Config,
    prog: Program,
    dt: frozenset[int],
    dtp: frozenset[int],
    da: frozenset[int],
    dap: frozenset[int],
) -> _Trace:
    W, R = cfg.word_bits, cfg.n_regs
    pcw = max(1, math.ceil(math.log2(len(prog))))
    # addr_bits == 0 ⇒ register-only programs; mem vars are absent so the
    # control scaffolding is small enough for `core.semantics`.
    mem = [b.fe(dt | da) for _ in range(W)] if cfg.addr_bits else []
    memp = [b.fe(dtp | dap) for _ in range(W)] if cfg.addr_bits else []
    reg = [[b.fe(dt) for _ in range(W)] for _ in range(R)]
    regp = [[b.fe(dtp) for _ in range(W)] for _ in range(R)]
    pc = [b.fe(dt) for _ in range(pcw)]
    pcp = [b.fe(dtp) for _ in range(pcw)]
    halt_idx = len(prog) - 1
    halted = b.eq_const(pc, halt_idx, dt)
    haltedp = b.eq_const(pcp, halt_idx, dtp)
    return _Trace(mem, memp, reg, regp, pc, pcp, halted, haltedp)


def _emit_step(
    b: _Builder,
    cfg: Config,
    prog: Program,
    tr: _Trace,
    STEP: int,
    a: list[int],
    ap: list[int],
    dt: frozenset[int],
    dall: frozenset[int],
) -> None:
    """Transition: STEP → state'(t') = δ(state(t)), dispatched on pc(t)."""
    W = cfg.word_bits
    pcw = len(tr.pc)
    succ_pc, _ = b.increment(tr.pc, dt)
    a_low = a[: cfg.addr_bits]
    ap_low = ap[: cfg.addr_bits]

    for idx, ins in enumerate(prog.instrs):
        at = b.eq_const(tr.pc, idx, dt)
        g = b.big_and([STEP, at], dall)

        # default next-pc = pc+1, overridden by BEQ/HALT below
        next_pc = succ_pc
        store_guard: int | None = None

        if ins.op == "MOV":
            rd, imm = ins.args
            const = [b.fe(dt) for _ in range(W)]
            for j, v in enumerate(const):
                b.clauses.append([v] if (imm >> j) & 1 else [-v])
            b.implies_iff(g, tr.regp[rd], const)
            for r in range(cfg.n_regs):
                if r != rd:
                    b.implies_iff(g, tr.regp[r], tr.reg[r])
        elif ins.op == "LOAD":
            rd, ra = ins.args
            # need mem(t, reg[ra]); reuse mem(t,a) by guarding on a==reg[ra]
            sel = b.eq_vec(a_low, tr.reg[ra][: cfg.addr_bits], dt | frozenset(a))
            gg = b.big_and([g, sel], dall)
            b.implies_iff(gg, tr.regp[rd], tr.mem)
            for r in range(cfg.n_regs):
                if r != rd:
                    b.implies_iff(g, tr.regp[r], tr.reg[r])
        elif ins.op == "STORE":
            ra, rs = ins.args
            sel = b.eq_vec(ap_low, tr.reg[ra][: cfg.addr_bits], dt | frozenset(ap))
            gg = b.big_and([g, sel], dall)
            b.implies_iff(gg, tr.memp, tr.reg[rs])
            store_guard = sel
            for r in range(cfg.n_regs):
                b.implies_iff(g, tr.regp[r], tr.reg[r])
        elif ins.op == "ADD":
            rd, ra, rb = ins.args
            s = b.ripple_add(tr.reg[ra], tr.reg[rb], dt)
            b.implies_iff(g, tr.regp[rd], s)
            for r in range(cfg.n_regs):
                if r != rd:
                    b.implies_iff(g, tr.regp[r], tr.reg[r])
        elif ins.op == "XOR":
            rd, ra, rb = ins.args
            x = []
            for j in range(W):
                e = b.fe(dt)
                b.t_iff(e, tr.reg[ra][j], -tr.reg[rb][j])
                x.append(-e)
            b.implies_iff(g, tr.regp[rd], x)
            for r in range(cfg.n_regs):
                if r != rd:
                    b.implies_iff(g, tr.regp[r], tr.reg[r])
        elif ins.op == "BEQ":
            ra, rb, tgt = ins.args
            eq = b.eq_vec(tr.reg[ra], tr.reg[rb], dt)
            tgt_bits = [b.fe(dt) for _ in range(pcw)]
            for j, v in enumerate(tgt_bits):
                b.clauses.append([v] if (tgt >> j) & 1 else [-v])
            taken = b.big_and([g, eq], dall)
            nottk = b.big_and([g, -eq], dall)
            b.implies_iff(taken, tr.pcp, tgt_bits)
            b.implies_iff(nottk, tr.pcp, succ_pc)
            for r in range(cfg.n_regs):
                b.implies_iff(g, tr.regp[r], tr.reg[r])
            next_pc = []  # handled
        elif ins.op == "HALT":
            for r in range(cfg.n_regs):
                b.implies_iff(g, tr.regp[r], tr.reg[r])
            b.implies_iff(g, tr.pcp, tr.pc)
            next_pc = []
        else:
            raise ValueError(f"unhandled op {ins.op}")

        if next_pc:
            b.implies_iff(g, tr.pcp, next_pc)

        # mem frame: addresses not written keep their value
        if cfg.addr_bits == 0:
            continue
        if store_guard is None:
            b.implies_iff(b.big_and([g, b.eq_vec(a_low, ap_low, dall)], dall), tr.memp, tr.mem)
        else:
            same = b.eq_vec(a_low, ap_low, dall)
            keep = b.big_and([g, same, -store_guard], dall)
            b.implies_iff(keep, tr.memp, tr.mem)


# --- public encoders ------------------------------------------------------


def encode_bounded(
    p: Program, q: Program, cfg: Config, source: str = "<memory>"
) -> Formula:
    b = _Builder(universals=[], deps={}, clauses=[])
    m = max(1, math.ceil(math.log2(max(cfg.bound, 2))))
    A = cfg.addr_bits

    t = [b.fu() for _ in range(m)]
    tp = [b.fu() for _ in range(m)]
    a = [b.fu() for _ in range(A)]
    ap = [b.fu() for _ in range(A)]
    dt, dtp = frozenset(t), frozenset(tp)
    da, dap = frozenset(a), frozenset(ap)
    dall = dt | dtp | da | dap

    EQt = b.eq_vec(t, tp, dt | dtp)
    EQa = b.eq_vec(a, ap, da | dap) if A else 0
    succ_t, ovf = b.increment(t, dt)
    STEP = b.big_and([b.eq_vec(tp, succ_t, dt | dtp), -ovf], dt | dtp)
    T0 = b.big_and([-ti for ti in t], dt)

    traces = {
        name: _alloc_trace(b, cfg, prog, dt, dtp, da, dap)
        for name, prog in (("P", p), ("Q", q))
    }

    for name, prog in (("P", p), ("Q", q)):
        tr = traces[name]
        # consistency: same Skolem function in both index copies
        if A:
            b.implies_iff(b.big_and([EQt, EQa], dall), tr.memp, tr.mem)
        b.implies_iff(EQt, sum(tr.regp, []), sum(tr.reg, []))
        b.implies_iff(EQt, tr.pcp, tr.pc)
        # init: t==0 → reg=0, pc=0
        for r in tr.reg:
            for v in r:
                b.clauses.append([-T0, -v])
        for v in tr.pc:
            b.clauses.append([-T0, -v])
        # step
        _emit_step(b, cfg, prog, tr, STEP, a, ap, dt, dall)

    # shared input: t==0 → memP(0,a) == memQ(0,a)
    if A:
        b.implies_iff(T0, traces["P"].mem, traces["Q"].mem)

    # equiv: both halted → out_reg agree
    both_halt = b.big_and([traces["P"].halted, traces["Q"].halted], dt)
    b.implies_iff(both_halt, traces["P"].reg[cfg.out_reg], traces["Q"].reg[cfg.out_reg])

    comments = (
        f"progequiv2dqbf bounded source={source}",
        f"P={p.name}({len(p)}) Q={q.name}({len(q)}) W={cfg.word_bits} A={A} K={cfg.bound}",
        "semantics: SAT = programs observationally equivalent within bound",
    )
    return make_formula(b.universals, b.deps, b.clauses, comments)


def product_transition(p: Program, q: Program, cfg: Config) -> Transition:
    """Product machine (state_P × state_Q) for the inductive-coupling
    encoding. Stub: full unrolling of one step into CNF; reuses
    `encode_indinv` for the prefix construction.
    """
    raise NotImplementedError(
        "product_transition: inductive-coupling stub — see README; "
        "fill in once the bounded encoding is validated"
    )


def encode_coupling(p: Program, q: Program, cfg: Config, source: str = "<memory>") -> Formula:
    return encode_indinv(product_transition(p, q, cfg), source=source)
