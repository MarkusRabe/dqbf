"""Third batch of parametric sequential circuits for BMC.

Each builder takes ``(n, bug)`` and returns ``(aag_text, comment, k_bad)``
where ``k_bad`` is the smallest BMC bound at which the bad state is
reachable (``None`` ⇒ unreachable). The ``bug`` flag injects a single
localised fault so that every circuit yields a balanced safe/buggy
pair: with ``bug=False`` the property holds (BMC is UNSAT for all k);
with ``bug=True`` it is reachable at ``k_bad``.

Circuit choices are textbook hardware blocks not already covered by
``circuits.py`` / ``circuits_v2.py``.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from tools.bmc2dqbf.circuits import FALSE_L, TRUE_L, B
from tools.bmc2dqbf.circuits_v2 import _const, _eq, _ripple_add, _ult


def _bits(n: int) -> int:
    return max(1, math.ceil(math.log2(max(2, n + 1))))


# --- circuits -------------------------------------------------------------


def circuit_traffic(n: int, bug: bool) -> tuple[str, str, int | None]:
    """4-phase traffic FSM with n-bit timer; bad = EW_green ∧ prev_NS_green.

    Phases (2-bit): 0=NSg, 1=NSy, 2=EWg, 3=EWy. Timer counts 2^n−1..0
    each phase; advance on zero. ``prev_nsg`` latches yesterday's NSg.

    Safe: NSg → NSy → EWg, so prev_NSg is false when EWg first holds.
    Bug: phase advance adds 2 (skips yellow), so NSg → EWg directly;
    on the first advance prev_nsg is still 1. Timer starts at 2^n−1
    (reset=1ⁿ), reaches 0 at step 2^n−1, phase advances at step 2^n,
    bad observed at step 2^n. ``k_bad = 2^n``.
    """
    b = B(n_inputs=0, n_latches=2 + n + 1)
    p = list(b.lats[:2])
    t = list(b.lats[2 : 2 + n])
    prev_nsg = b.lats[2 + n]
    zero = b.all_and([b.gNOT(x) for x in t])
    dec, _ = _ripple_add(b, t, _const(n, (1 << n) - 1))
    npv, _ = _ripple_add(b, p, _const(2, 2 if bug else 1))
    for i in range(2):
        b.set_next(p[i], b.gMUX(zero, npv[i], p[i]))
    for i in range(n):
        b.set_next(t[i], b.gMUX(zero, TRUE_L, dec[i]), reset=1)
    ns_g = b.gAND(b.gNOT(p[0]), b.gNOT(p[1]))
    ew_g = b.gAND(b.gNOT(p[0]), p[1])
    b.set_next(prev_nsg, ns_g, reset=1)
    bad = b.gAND(ew_g, prev_nsg)
    return b.aag(bad), f"traffic n={n} bug={bug}", (1 << n) if bug else None


def circuit_crc(n: int, bug: bool) -> tuple[str, str, int | None]:
    """n-bit CRC register vs an identically-tapped shadow; bad = r ≠ z.

    Input: ``d`` (1 bit/cycle). Both ``r`` and ``z`` shift with feedback
    ``d ⊕ ⨁ r[taps]``.

    Safe: same taps → bitwise identical → UNSAT.
    Bug: shadow's feedback omits the XOR with ``d``, so the very first
    1 on ``d`` makes ``r[0]≠z[0]`` the next cycle. ``k_bad = 1``.
    """
    taps = {4: (3, 0), 8: (7, 5, 4, 3), 12: (11, 10, 7, 5),
            16: (15, 14, 12, 3), 20: (19, 16), 24: (23, 22, 21, 16),
            32: (31, 21, 1, 0)}.get(n, (n - 1, 0))
    b = B(n_inputs=1, n_latches=2 * n)
    d = b.ins[0]
    r, z = list(b.lats[:n]), list(b.lats[n:])
    fb_r = d
    for t in taps:
        fb_r = b.gXOR(fb_r, r[t])
    fb_z = FALSE_L if bug else d
    for t in taps:
        fb_z = b.gXOR(fb_z, z[t])
    for i in range(n):
        b.set_next(r[i], fb_r if i == 0 else r[i - 1])
        b.set_next(z[i], fb_z if i == 0 else z[i - 1])
    bad = b.gNOT(_eq(b, r, z))
    return b.aag(bad), f"crc n={n} bug={bug}", 1 if bug else None


def circuit_lzc(n: int, bug: bool) -> tuple[str, str, int | None]:
    """Leading-zero count (MSB-first) of n-bit input; bad = cnt > n.

    Bug: the all-zero arm outputs n+1 instead of n. ``k_bad = 1``.
    """
    cw = _bits(n + 1)
    b = B(n_inputs=n, n_latches=cw)
    x = list(b.ins)
    cnt = list(b.lats)
    higher = FALSE_L
    val = _const(cw, 0)
    for i in range(n):
        bit = x[n - 1 - i]
        hit = b.gAND(bit, b.gNOT(higher))
        ci = _const(cw, i)
        val = [b.gMUX(hit, ci[j], val[j]) for j in range(cw)]
        higher = b.gOR(higher, bit)
    nz = _const(cw, n + (1 if bug else 0))
    val = [b.gMUX(b.gNOT(higher), nz[j], val[j]) for j in range(cw)]
    for j in range(cw):
        b.set_next(cnt[j], val[j])
    bad = _ult(b, _const(cw, n), cnt)
    return b.aag(bad), f"lzc n={n} bug={bug}", 1 if bug else None


def circuit_barrel(n: int, bug: bool) -> tuple[str, str, int | None]:
    """n-bit barrel rotate-left; bad = (s==0) ∧ out ≠ x.

    Bug: stage-0 mux select is stuck-at-1, so even s=0 rotates by 1.
    ``k_bad = 1`` (any non-uniform x with s=0).
    """
    sw = _bits(n - 1)
    b = B(n_inputs=n + sw, n_latches=2 * n + sw)
    x = list(b.ins[:n])
    s = list(b.ins[n:])
    out = list(b.lats[:n])
    sx = list(b.lats[n : 2 * n])
    ss = list(b.lats[2 * n :])
    cur = list(x)
    for stage in range(sw):
        step = (1 << stage) % n
        rot = [cur[(i + step) % n] for i in range(n)]
        sel = TRUE_L if (bug and stage == 0) else s[stage]
        cur = [b.gMUX(sel, rot[i], cur[i]) for i in range(n)]
    for i in range(n):
        b.set_next(out[i], cur[i])
        b.set_next(sx[i], x[i])
    for j in range(sw):
        b.set_next(ss[j], s[j])
    bad = b.gAND(b.all_and([b.gNOT(v) for v in ss]), b.gNOT(_eq(b, out, sx)))
    return b.aag(bad), f"barrel n={n} bug={bug}", 1 if bug else None


def circuit_bcd_ctr(n: int, bug: bool) -> tuple[str, str, int | None]:
    """n-digit BCD up-counter; bad = any digit > 9.

    Bug: digit-0 wrap test compares against 10, so it reaches 10 before
    wrapping. Deterministic, ``k_bad = 10``.
    """
    b = B(n_inputs=0, n_latches=4 * n)
    digs = [list(b.lats[4 * i : 4 * i + 4]) for i in range(n)]
    carry = TRUE_L
    for i, d in enumerate(digs):
        limit = 10 if (bug and i == 0) else 9
        wrap = b.gAND(carry, _eq(b, d, _const(4, limit)))
        inc, _ = _ripple_add(b, d, _const(4, 1))
        for j in range(4):
            b.set_next(d[j], b.gMUX(wrap, FALSE_L, b.gMUX(carry, inc[j], d[j])))
        carry = wrap
    bad = b.any_or([_ult(b, _const(4, 9), d) for d in digs])
    return b.aag(bad), f"bcd_ctr n={n} bug={bug}", 10 if bug else None


def circuit_debounce(n: int, bug: bool) -> tuple[str, str, int | None]:
    """n-cycle debounce stability counter; bad = cnt > n.

    Input: ``d``. Latches: ``cnt``, ``prev_d``. ``cnt`` increments while
    ``d==prev_d``, saturating at n; resets to 0 on change.

    Safe: saturation holds ``cnt ≤ n`` → UNSAT.
    Bug: saturation removed; with ``d`` held constant ``cnt`` reaches
    n+1 at step n+1. ``k_bad = n+1``.
    """
    cw = _bits(n + 1)
    b = B(n_inputs=1, n_latches=cw + 1)
    d = b.ins[0]
    cnt = list(b.lats[:cw])
    prev_d = b.lats[cw]
    stable = b.gNOT(b.gXOR(d, prev_d))
    inc, _ = _ripple_add(b, cnt, _const(cw, 1))
    at_n = _eq(b, cnt, _const(cw, n))
    sat = FALSE_L if bug else at_n
    for j in range(cw):
        b.set_next(cnt[j], b.gMUX(stable, b.gMUX(sat, cnt[j], inc[j]), FALSE_L))
    b.set_next(prev_d, d)
    bad = _ult(b, _const(cw, n), cnt)
    return b.aag(bad), f"debounce n={n} bug={bug}", (n + 1) if bug else None


def circuit_spi_ctrl(n: int, bug: bool) -> tuple[str, str, int | None]:
    """SPI shift controller; bad = done ∧ cnt ≠ n.

    Bug: done fires at cnt==n-1. After load at step 0, cnt increments
    each busy cycle: cnt=0@1, 1@2, …, (n-1)@n; done'@n = busy∧hit ⇒
    done=1 at step n with cnt=n-1 latched. But cnt also advances that
    cycle. Trace: step t has cnt=t-1 for t≥1; hit when t-1==n-1 i.e.
    t=n; done latches at t=n+1 with cnt' = n. So bad never fires.
    Fix: freeze cnt when done fires. Then at t=n+1: done=1, cnt=n-1.
    """
    cw = _bits(n)
    b = B(n_inputs=1, n_latches=cw + 2)
    load = b.ins[0]
    cnt = list(b.lats[:cw])
    busy, done = b.lats[cw], b.lats[cw + 1]
    inc, _ = _ripple_add(b, cnt, _const(cw, 1))
    target = n - 1 if bug else n
    hit = _eq(b, cnt, _const(cw, target))
    advance = b.gAND(busy, b.gNOT(hit))
    for j in range(cw):
        b.set_next(cnt[j], b.gMUX(load, FALSE_L, b.gMUX(advance, inc[j], cnt[j])))
    b.set_next(busy, b.gMUX(load, TRUE_L, b.gAND(busy, b.gNOT(hit))))
    # Gate done on ¬load so a same-cycle reload can't desync cnt.
    b.set_next(done, b.gAND(b.gAND(busy, hit), b.gNOT(load)))
    bad = b.gAND(done, b.gNOT(_eq(b, cnt, _const(cw, n))))
    return b.aag(bad), f"spi_ctrl n={n} bug={bug}", (n + 1) if bug else None


def circuit_prio_enc(n: int, bug: bool) -> tuple[str, str, int | None]:
    """n-input priority encoder; bad = valid ∧ ¬sx[idx].

    Bug: encoder ignores the top input ``x[n-1]``; a request with only
    that bit set yields valid=1, idx=0, sx[0]=0. ``k_bad = 1``.
    """
    iw = _bits(n - 1)
    b = B(n_inputs=n, n_latches=iw + 1 + n)
    x = list(b.ins)
    idx = list(b.lats[:iw])
    valid = b.lats[iw]
    sx = list(b.lats[iw + 1 :])
    higher = FALSE_L
    val = _const(iw, 0)
    for i in range(n - 1, -1, -1):
        if bug and i == n - 1:
            continue
        hit = b.gAND(x[i], b.gNOT(higher))
        ci = _const(iw, i)
        val = [b.gMUX(hit, ci[j], val[j]) for j in range(iw)]
        higher = b.gOR(higher, x[i])
    for j in range(iw):
        b.set_next(idx[j], val[j])
    b.set_next(valid, b.any_or(x))
    for i in range(n):
        b.set_next(sx[i], x[i])
    picked = sx[0]
    for i in range(1, n):
        picked = b.gMUX(_eq(b, idx, _const(iw, i)), sx[i], picked)
    bad = b.gAND(valid, b.gNOT(picked))
    return b.aag(bad), f"prio_enc n={n} bug={bug}", 1 if bug else None


def circuit_parity_pipe(n: int, bug: bool) -> tuple[str, str, int | None]:
    """2-stage pipelined XOR-reduce vs single-cycle reference.

    Inputs: ``x[n]``. Latches: ``sx[n]``, ``p_pipe``, ``p_ref``.
    Both compute ⊕x over the *same* registered ``sx``.

    Bug: pipe drops ``sx[0]`` from its XOR. ``k_bad = 1`` (x with
    x[0]=1, rest=0 ⇒ sx differs in bit 0 ⇒ parities differ at step 2;
    actually both latch from sx so need 2 cycles). Trace: x@0 latched
    to sx@1; p_pipe',p_ref' computed from sx@1 latched at step 2.
    ``k_bad = 2``.
    """
    b = B(n_inputs=n, n_latches=n + 2)
    x = list(b.ins)
    sx = list(b.lats[:n])
    p_pipe, p_ref = b.lats[n], b.lats[n + 1]
    for i in range(n):
        b.set_next(sx[i], x[i])
    src_pipe = sx[1:] if bug else sx
    pp = FALSE_L
    for v in src_pipe:
        pp = b.gXOR(pp, v)
    pr = FALSE_L
    for v in sx:
        pr = b.gXOR(pr, v)
    b.set_next(p_pipe, pp)
    b.set_next(p_ref, pr)
    bad = b.gXOR(p_pipe, p_ref)
    return b.aag(bad), f"parity_pipe n={n} bug={bug}", 2 if bug else None


def circuit_updown(n: int, bug: bool) -> tuple[str, str, int | None]:
    """n-bit up/down counter with bounds; bad = underflow (borrow at 0).

    Input: ``dir`` (1=up, 0=down). Latches: ``c[n]``, ``uflow``.
    Down at 0 should hold (saturate); ``uflow`` records a borrow.

    Bug: down does not saturate. ``k_bad = 1`` (dir=0 at reset).
    """
    b = B(n_inputs=1, n_latches=n + 1)
    dr = b.ins[0]
    c = list(b.lats[:n])
    uflow = b.lats[n]
    inc, _ = _ripple_add(b, c, _const(n, 1))
    dec, no_borrow = _ripple_add(b, c, _const(n, (1 << n) - 1), cin=FALSE_L)
    is_zero = b.all_and([b.gNOT(v) for v in c])
    down_ok = b.gNOT(is_zero) if not bug else TRUE_L
    do_down = b.gAND(b.gNOT(dr), down_ok)
    for i in range(n):
        b.set_next(c[i], b.gMUX(dr, inc[i], b.gMUX(do_down, dec[i], c[i])))
    b.set_next(uflow, b.gAND(b.gNOT(dr), b.gAND(down_ok, is_zero)))
    return b.aag(uflow), f"updown n={n} bug={bug}", 1 if bug else None


def circuit_hamming(n: int, bug: bool) -> tuple[str, str, int | None]:
    """Two-copy n-bit register; bad = popcount(a⊕b) > 0 (Hamming dist).

    Inputs: ``we``, ``d[n]``. Both copies load identically.
    Safe: identical wiring → UNSAT. Bug: copy-b bit 0 latches ¬d[0].
    ``k_bad = 1`` (any write).
    """
    b = B(n_inputs=1 + n, n_latches=2 * n)
    we = b.ins[0]
    d = list(b.ins[1:])
    a, c = list(b.lats[:n]), list(b.lats[n:])
    for i in range(n):
        b.set_next(a[i], b.gMUX(we, d[i], a[i]))
        src = b.gNOT(d[i]) if (bug and i == 0) else d[i]
        b.set_next(c[i], b.gMUX(we, src, c[i]))
    bad = b.any_or([b.gXOR(a[i], c[i]) for i in range(n)])
    return b.aag(bad), f"hamming n={n} bug={bug}", 1 if bug else None


CircuitFn = Callable[[int, bool], tuple[str, str, int | None]]

REGISTRY_V3: dict[str, CircuitFn] = {
    "traffic": circuit_traffic,
    "crc": circuit_crc,
    "lzc": circuit_lzc,
    "barrel": circuit_barrel,
    "bcd_ctr": circuit_bcd_ctr,
    "debounce": circuit_debounce,
    "spi_ctrl": circuit_spi_ctrl,
    "prio_enc": circuit_prio_enc,
    "parity_pipe": circuit_parity_pipe,
    "updown": circuit_updown,
    "hamming": circuit_hamming,
}
