"""Second batch of parametric sequential circuits for BMC.

Each circuit composes multiple operations (ripple add/sub, mux trees,
comparators, shift, one-hot decode) so the bit-blasted unrolling has
non-trivial structure. Roughly half are SAT (bad reachable) and half
are UNSAT (correctness invariants).
"""

from __future__ import annotations

from collections.abc import Callable

from tools.bmc2dqbf.circuits import FALSE_L, TRUE_L, B

# --- combinational helpers -----------------------------------------------


def _ripple_add(b: B, xs: list[int], ys: list[int], cin: int = FALSE_L) -> tuple[list[int], int]:
    """LSB-first ripple add; returns (sum_bits, carry_out)."""
    out: list[int] = []
    c = cin
    for x, y in zip(xs, ys, strict=True):
        s = b.gXOR(b.gXOR(x, y), c)
        c = b.gOR(b.gAND(x, y), b.gAND(c, b.gXOR(x, y)))
        out.append(s)
    return out, c


def _ripple_sub(b: B, xs: list[int], ys: list[int]) -> tuple[list[int], int]:
    """xs - ys via xs + ~ys + 1; carry_out=1 ⇔ no borrow ⇔ xs ≥ ys."""
    return _ripple_add(b, xs, [b.gNOT(y) for y in ys], cin=TRUE_L)


def _eq(b: B, xs: list[int], ys: list[int]) -> int:
    return b.all_and([b.gNOT(b.gXOR(x, y)) for x, y in zip(xs, ys, strict=True)])


def _ult(b: B, xs: list[int], ys: list[int]) -> int:
    """Unsigned xs < ys: borrow-out of xs - ys."""
    _, no_borrow = _ripple_sub(b, xs, ys)
    return b.gNOT(no_borrow)


def _const(n: int, v: int) -> list[int]:
    return [TRUE_L if (v >> i) & 1 else FALSE_L for i in range(n)]


# --- circuits -------------------------------------------------------------


def circuit_alu4op(n: int) -> tuple[str, str]:
    """n-bit 4-op ALU with a 2-bit opcode counter.

    Inputs: `a[n]`, `c[n]` operands per cycle.
    Latches: `op[2]` (00→01→10→11→00 each cycle), `out[n]` registered ALU
    result.
    Ops: 00=add, 01=sub, 10=and, 11=or.
    Bad: `out == 2^n − 1` ∧ `op == 01` (just *after* a sub produced
    all-ones, i.e. inputs satisfied a − c = −1).

    Reachability: SAT — drive (a=0, c=1) on the cycle where op=01; bad
    holds the next cycle. Needs k ≥ 2 (op must reach 01 first, then one
    more cycle to latch). For BMC@k: SAT iff k ≥ 2.
    """
    b = B(n_inputs=2 * n, n_latches=2 + n)
    a, c = b.ins[:n], b.ins[n:]
    op0, op1 = b.lats[0], b.lats[1]
    out = b.lats[2:]
    # op counter
    b.set_next(op0, b.gNOT(op0))
    b.set_next(op1, b.gXOR(op1, op0))
    # ops
    s_add, _ = _ripple_add(b, a, c)
    s_sub, _ = _ripple_sub(b, a, c)
    s_and = [b.gAND(x, y) for x, y in zip(a, c, strict=True)]
    s_or = [b.gOR(x, y) for x, y in zip(a, c, strict=True)]
    # 2-level mux: op1 ? (op0?or:and) : (op0?sub:add)
    lo = [b.gMUX(op0, s_sub[i], s_add[i]) for i in range(n)]
    hi = [b.gMUX(op0, s_or[i], s_and[i]) for i in range(n)]
    for i in range(n):
        b.set_next(out[i], b.gMUX(op1, hi[i], lo[i]))
    bad = b.gAND(b.all_and(list(out)), b.gAND(op0, b.gNOT(op1)))
    return b.aag(bad), f"alu4op n={n}: bad = (out==-1) right after a sub"


def circuit_lfsr(n: int) -> tuple[str, str]:
    """n-bit Fibonacci LFSR (no inputs), seeded at 1.

    Latches: `s[n]`, reset = 0…01.
    Transition: `s[0]' = XOR of taps`, `s[i]' = s[i-1]`.
    Taps: hard-coded maximal polynomials for n∈{2..8}; for other n a
    non-maximal `[n-1, 0]` pair (still cycles, just shorter period).
    Bad: state == seed (i.e. `s = 0…01`).

    Reachability: bad holds at k=0 and again at k=period. With the
    standard "bad reachable at some t≤k" BMC, SAT for every k≥0 (period
    detection is the *second* hit). The interest is the encoding cost,
    not the threshold.
    """
    taps = {2: [1, 0], 3: [2, 1], 4: [3, 2], 5: [4, 2], 6: [5, 4], 7: [6, 5], 8: [7, 5, 4, 3]}
    tp = taps.get(n, [n - 1, 0])
    b = B(n_inputs=0, n_latches=n)
    s = b.lats
    fb = s[tp[0]]
    for t in tp[1:]:
        fb = b.gXOR(fb, s[t])
    for i in range(n):
        b.set_next(s[i], fb if i == 0 else s[i - 1], reset=(1 if i == 0 else 0))
    seed = _const(n, 1)
    bad = _eq(b, list(s), seed)
    return b.aag(bad), f"lfsr n={n}: bad = state==seed (period hit)"


def circuit_sat_accum(n: int) -> tuple[str, str]:
    """Saturating n-bit accumulator with overflow-loss detector.

    Inputs: `d[n]` value per cycle.
    Latches: `acc[n]`, `sat` (sticky saturation flag), `lost` (sticky:
    a nonzero `d` arrived while already saturated).
    Transition: `(sum, c) = acc + d`; `acc' = c ? all-ones : sum`;
    `sat' = sat ∨ c`; `lost' = lost ∨ (sat ∧ OR(d))`.
    Bad: `lost`.

    Reachability: SAT — drive d=all-ones twice (sat after step 1, lost
    after step 2). BMC@k SAT iff k ≥ 2.
    """
    b = B(n_inputs=n, n_latches=n + 2)
    d = b.ins
    acc = b.lats[:n]
    sat, lost = b.lats[n], b.lats[n + 1]
    s, c = _ripple_add(b, list(acc), list(d))
    for i in range(n):
        b.set_next(acc[i], b.gOR(s[i], c))  # mux to all-ones when c
    b.set_next(sat, b.gOR(sat, c))
    b.set_next(lost, b.gOR(lost, b.gAND(sat, b.any_or(list(d)))))
    return b.aag(lost), f"sat_accum n={n}: bad = data lost after saturation"


def circuit_minmax(n: int) -> tuple[str, str]:
    """Running min/max tracker over an n-bit input stream.

    Inputs: `d[n]` per cycle.
    Latches: `mn[n]` (reset all-ones), `mx[n]` (reset 0).
    Transition: `mn' = (d < mn) ? d : mn`; `mx' = (d > mx) ? d : mx`.
    Bad: `mn == 0 ∧ mx == 2^n−1` (full range observed).

    Reachability: SAT — drive d=0 then d=all-ones. BMC@k SAT iff k ≥ 2.
    """
    b = B(n_inputs=n, n_latches=2 * n)
    d = list(b.ins)
    mn, mx = list(b.lats[:n]), list(b.lats[n:])
    lt_mn = _ult(b, d, mn)
    gt_mx = _ult(b, mx, d)
    for i in range(n):
        b.set_next(mn[i], b.gMUX(lt_mn, d[i], mn[i]), reset=1)
        b.set_next(mx[i], b.gMUX(gt_mx, d[i], mx[i]), reset=0)
    bad = b.gAND(b.all_and([b.gNOT(x) for x in mn]), b.all_and(mx))
    return b.aag(bad), f"minmax n={n}: bad = full range (0 and -1) seen"


def circuit_modmul(n: int) -> tuple[str, str]:
    """Iterated x ← (3·x) mod 2^n, seeded at 1 (no inputs).

    Latches: `x[n]`, reset = 1.
    Transition: `x' = x + (x << 1)` (i.e. 3x mod 2^n).
    Bad: `x == 1` ∧ `step ≥ 1` (returned to seed). To detect "step≥1"
    a 1-bit `started` latch is added.

    Reachability: SAT at k = ord(3 mod 2^n) = 2^(n-2) for n≥3 (and 1
    for n=1,2). For N=4 SAT from k=4; N=8 from k=64.
    """
    b = B(n_inputs=0, n_latches=n + 1)
    x = list(b.lats[:n])
    started = b.lats[n]
    shl = [FALSE_L] + x[:-1]
    s, _ = _ripple_add(b, x, shl)
    for i in range(n):
        b.set_next(x[i], s[i], reset=(1 if i == 0 else 0))
    b.set_next(started, TRUE_L)
    bad = b.gAND(started, _eq(b, x, _const(n, 1)))
    return b.aag(bad), f"modmul n={n}: bad = 3^k ≡ 1 (mod 2^{n})"


def circuit_ringbuf(n: int) -> tuple[str, str]:
    """2-slot 1-bit ring buffer with shadow check (push/pop inputs).

    Inputs: `push`, `pop`, `d` (1-bit data); n controls pointer width
    only loosely — here we keep 2 slots regardless of n and use n only
    to widen the *data* path: data is n bits.
    Latches: `wr` (1b), `rd` (1b), `mem0[n]`, `mem1[n]`, `shadow[n]`
    (last value written), `valid` (something has been written).
    Bad: `pop ∧ valid ∧ (mem[rd] ≠ shadow)` when `wr==rd⊕1` (i.e.
    exactly one item in flight).

    Reachability: UNSAT — with one item in flight the slot read is
    exactly the last slot written. BMC@k UNSAT for every k.
    """
    b = B(n_inputs=2 + n, n_latches=2 + 3 * n + 1)
    push, pop = b.ins[0], b.ins[1]
    d = list(b.ins[2:])
    wr, rd = b.lats[0], b.lats[1]
    mem0 = list(b.lats[2 : 2 + n])
    mem1 = list(b.lats[2 + n : 2 + 2 * n])
    shadow = list(b.lats[2 + 2 * n : 2 + 3 * n])
    valid = b.lats[2 + 3 * n]
    # write
    w0 = b.gAND(push, b.gNOT(wr))
    w1 = b.gAND(push, wr)
    for i in range(n):
        b.set_next(mem0[i], b.gMUX(w0, d[i], mem0[i]))
        b.set_next(mem1[i], b.gMUX(w1, d[i], mem1[i]))
        b.set_next(shadow[i], b.gMUX(push, d[i], shadow[i]))
    b.set_next(wr, b.gXOR(wr, push))
    b.set_next(rd, b.gXOR(rd, pop))
    b.set_next(valid, b.gOR(valid, push))
    # read mux + compare
    rsel = [b.gMUX(rd, mem1[i], mem0[i]) for i in range(n)]
    one_item = b.gXOR(wr, rd)
    bad = b.gAND(b.gAND(pop, b.gAND(valid, one_item)), b.gNOT(_eq(b, rsel, shadow)))
    return b.aag(bad), f"ringbuf n={n}: bad = read ≠ last-written under one-in-flight"


def circuit_rr_arbiter(n: int) -> tuple[str, str]:
    """n-way round-robin arbiter with starvation monitor on requester 0.

    Inputs: `req[n]` per cycle.
    Latches: `ptr[n]` (one-hot, reset = bit0), `wait[n]` (saturating
    unary counter of consecutive cycles req[0]∧¬grant[0]).
    Grant (combinational): for each i, `grant[i] = req[i] ∧ ptr[i]`;
    `ptr' = rotate-left(ptr)`.
    Bad: `wait` is all-ones (req[0] starved for n cycles).

    Reachability: UNSAT — round-robin guarantees grant[0] within n
    cycles. BMC@k UNSAT for every k.
    """
    b = B(n_inputs=n, n_latches=2 * n)
    req = list(b.ins)
    ptr = list(b.lats[:n])
    wait = list(b.lats[n:])
    for i in range(n):
        b.set_next(ptr[i], ptr[(i - 1) % n], reset=(1 if i == 0 else 0))
    grant0 = b.gAND(req[0], ptr[0])
    starv = b.gAND(req[0], b.gNOT(grant0))
    # wait is unary saturating: shift in `starv`, clear on ¬starv
    for i in range(n):
        prev = wait[i - 1] if i > 0 else TRUE_L
        b.set_next(wait[i], b.gAND(starv, prev))
    bad = b.all_and(wait)
    return b.aag(bad), f"rr_arbiter n={n}: bad = req0 starved {n} cycles"


def circuit_onehot_fsm(n: int) -> tuple[str, str]:
    """One-hot n-state ring FSM with input-gated advance.

    Input: `go` (1 bit).
    Latches: `s[n]` (one-hot, reset = bit0).
    Transition: `s' = go ? rotate-left(s) : s`.
    Bad: not-exactly-one-hot.

    Reachability: UNSAT — rotation and hold both preserve one-hot.
    """
    b = B(n_inputs=1, n_latches=n)
    go = b.ins[0]
    s = list(b.lats)
    for i in range(n):
        b.set_next(s[i], b.gMUX(go, s[(i - 1) % n], s[i]), reset=(1 if i == 0 else 0))
    at_least_one = b.any_or(s)
    pairs = [b.gAND(s[i], s[j]) for i in range(n) for j in range(i + 1, n)]
    at_most_one = b.gNOT(b.any_or(pairs))
    bad = b.gNOT(b.gAND(at_least_one, at_most_one))
    return b.aag(bad), f"onehot_fsm n={n}: bad = not one-hot"


def circuit_cmp_pipe(n: int) -> tuple[str, str]:
    """2-stage pipelined `a < b` vs single-cycle reference.

    Inputs: `a[n]`, `c[n]`.
    Latches: `sa[n]`, `sc[n]` (stage-1 regs), `lt_pipe` (stage-2
    output), `lt_ref` (reference computed from sa,sc).
    Bad: `lt_pipe ⊕ lt_ref`.

    Reachability: UNSAT — both compute the same `<` on the same
    registered operands. BMC@k UNSAT for every k.
    """
    b = B(n_inputs=2 * n, n_latches=2 * n + 2)
    a, c = list(b.ins[:n]), list(b.ins[n:])
    sa, sc = list(b.lats[:n]), list(b.lats[n : 2 * n])
    lt_pipe, lt_ref = b.lats[2 * n], b.lats[2 * n + 1]
    for i in range(n):
        b.set_next(sa[i], a[i])
        b.set_next(sc[i], c[i])
    b.set_next(lt_pipe, _ult(b, list(sa), list(sc)))
    b.set_next(lt_ref, _ult(b, list(sa), list(sc)))
    bad = b.gXOR(lt_pipe, lt_ref)
    return b.aag(bad), f"cmp_pipe n={n}: bad = pipelined < ≠ reference"


def circuit_uart_tx(n: int) -> tuple[str, str]:
    """UART-style serializer: start(0), n data bits LSB-first, stop(1).

    Inputs: `load`, `d[n]`.
    Latches: `sh[n]` (shift reg), `cnt[⌈log₂(n+3)⌉]` (bit counter),
    `busy`.
    Bad: `busy ∧ cnt-overflow` — counter wrapped past the stop bit
    without `busy` clearing (frame ran long).

    Reachability: UNSAT — `done` (cnt==n+1) clears `busy` before the
    counter can reach 2^cw−1. BMC@k UNSAT for every k.
    """
    import math

    cw = max(2, math.ceil(math.log2(n + 3)))
    b = B(n_inputs=1 + n, n_latches=n + cw + 1)
    load = b.ins[0]
    d = list(b.ins[1:])
    sh = list(b.lats[:n])
    cnt = list(b.lats[n : n + cw])
    busy = b.lats[n + cw]
    inc, c_out = _ripple_add(b, cnt, _const(cw, 1))
    done = _eq(b, cnt, _const(cw, n + 1))
    advance = b.gAND(busy, b.gNOT(load))
    for i in range(cw):
        b.set_next(cnt[i], b.gMUX(advance, inc[i], b.gAND(b.gNOT(load), cnt[i])))
    b.set_next(busy, b.gMUX(busy, b.gNOT(done), load))
    for i in range(n):
        shifted = sh[i + 1] if i + 1 < n else TRUE_L
        b.set_next(sh[i], b.gMUX(load, d[i], b.gMUX(advance, shifted, sh[i])))
    bad = b.gAND(busy, c_out)
    return b.aag(bad), f"uart_tx n={n}: bad = bit-counter overran frame"


REGISTRY_V2: dict[str, Callable[[int], tuple[str, str]]] = {
    "alu4op": circuit_alu4op,
    "lfsr": circuit_lfsr,
    "sat_accum": circuit_sat_accum,
    "minmax": circuit_minmax,
    "modmul": circuit_modmul,
    "ringbuf": circuit_ringbuf,
    "rr_arbiter": circuit_rr_arbiter,
    "onehot_fsm": circuit_onehot_fsm,
    "cmp_pipe": circuit_cmp_pipe,
    "uart_tx": circuit_uart_tx,
}
