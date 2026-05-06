"""C-algorithm-style sequential circuits for the cbmc benchmark family.

Each entry models a small single-loop C program at the bit level: state
variables become latches, the loop body becomes the transition relation,
and the post-loop `__CPROVER_assert` becomes the bad signal (negated, so
SAT ⇔ assertion can fail). Every algorithm comes in an `_ok` and a
`_bug` variant — same state, one defect — giving a balanced reachable /
unreachable split with matched structure.

These feed `encode_succinct` to produce genuine DQBF (latches as
∃-functions of a universal step counter), letting the same C corpus be
benchmarked under both the flat CBMC encoding and the succinct DQBF
encoding.

Expected reachability is **derived analytically** from the algorithm,
never from a solver run.
"""

from __future__ import annotations

from collections.abc import Callable

from tools.bmc2dqbf.circuits import FALSE_L, TRUE_L, B
from tools.bmc2dqbf.circuits_v2 import _const, _eq, _ripple_add, _ripple_sub, _ult


def _mux_word(b: B, c: int, ts: list[int], es: list[int]) -> list[int]:
    return [b.gMUX(c, t, e) for t, e in zip(ts, es, strict=True)]


def _is_zero(b: B, xs: list[int]) -> int:
    return b.all_and([b.gNOT(x) for x in xs])


def _inc(b: B, xs: list[int]) -> list[int]:
    s, _ = _ripple_add(b, xs, _const(len(xs), 0), cin=TRUE_L)
    return s


def _shl1(xs: list[int]) -> list[int]:
    return [FALSE_L] + xs[:-1]


def _shr1(xs: list[int]) -> list[int]:
    return xs[1:] + [FALSE_L]


# --- popcount: shift x right, accumulate LSB into c -----------------------


def circuit_popcount(n: int, bug: bool) -> tuple[str, str, str]:
    """Iterative popcount: while x≠0 { c += x&1; x >>= 1 }.

    Latches: init, x[n], c[n], seed[n].
    Phase 0 (init=0): load nondet input into x and seed; set init=1.
    Phase 1 (init=1, x≠0): c += x[0]; x >>= 1.
    Bad: init ∧ x==0 ∧ c ≠ popcount(seed).

    The `_bug` variant shifts x right *before* sampling its LSB, so the
    seed's LSB never gets counted — popcount is off whenever seed is odd.
    Reachable for any n≥1 (seed=1 gives c=0, true count=1).

    The `_ok` variant is correct; bad unreachable. Expected: ok→UNSAT,
    bug→SAT (after ≥ n+1 steps).
    """
    b = B(n_inputs=n, n_latches=1 + 3 * n)
    init = b.lats[0]
    x = b.lats[1 : 1 + n]
    c = b.lats[1 + n : 1 + 2 * n]
    seed = b.lats[1 + 2 * n : 1 + 3 * n]
    seed_in = list(b.ins)
    nz = b.gNOT(_is_zero(b, x))
    run = b.gAND(init, nz)
    sampled = _shr1(x)[0] if bug else x[0]
    c1, _ = _ripple_add(b, c, _const(n, 0), cin=sampled)
    x1 = _shr1(x)
    b.set_next(init, TRUE_L)
    for i in range(n):
        b.set_next(x[i], b.gMUX(init, b.gMUX(run, x1[i], x[i]), seed_in[i]))
        b.set_next(c[i], b.gMUX(run, c1[i], c[i]))
        b.set_next(seed[i], b.gMUX(init, seed[i], seed_in[i]))
    # reference popcount of seed (combinational)
    ref = _const(n, 0)
    for i in range(n):
        ref, _ = _ripple_add(b, ref, _const(n, 0), cin=seed[i])
    bad = b.gAND(b.gAND(init, _is_zero(b, x)), b.gNOT(_eq(b, c, ref)))
    return b.aag(bad), ("sat" if bug else "unsat"), f"popcount n={n} bug={bug}"


# --- parity: fold XOR of bits ---------------------------------------------


def circuit_parity(n: int, bug: bool) -> tuple[str, str, str]:
    """Iterative parity: while x≠0 { p ^= x&1; x >>= 1 }.

    Bug: p reset to 1 instead of 0 (so result is ¬parity).
    ok→UNSAT, bug→SAT (any seed with even parity, e.g. seed=0, gives
    p=1≠0 once init completes).
    """
    b = B(n_inputs=n, n_latches=2 + 2 * n)
    init = b.lats[0]
    p = b.lats[1]
    x = b.lats[2 : 2 + n]
    seed = b.lats[2 + n : 2 + 2 * n]
    seed_in = list(b.ins)
    nz = b.gNOT(_is_zero(b, x))
    run = b.gAND(init, nz)
    p1 = b.gXOR(p, x[0])
    x1 = _shr1(x)
    b.set_next(init, TRUE_L)
    b.set_next(p, b.gMUX(init, b.gMUX(run, p1, p), TRUE_L if bug else FALSE_L))
    for i in range(n):
        b.set_next(x[i], b.gMUX(init, b.gMUX(run, x1[i], x[i]), seed_in[i]))
        b.set_next(seed[i], b.gMUX(init, seed[i], seed_in[i]))
    ref = FALSE_L
    for s in seed:
        ref = b.gXOR(ref, s)
    bad = b.gAND(b.gAND(init, _is_zero(b, x)), b.gXOR(p, ref))
    return b.aag(bad), ("sat" if bug else "unsat"), f"parity n={n} bug={bug}"


# --- bitrev: shift x→y bit-by-bit -----------------------------------------


def circuit_bitrev(n: int, bug: bool) -> tuple[str, str, str]:
    """Bit-reverse via shift: for i<n { y = (y<<1)|x[0]; x >>= 1 }.

    Bug: shifts y *right* instead of left — produces y==x>>? not the
    reversal. ok→UNSAT, bug→SAT (e.g. seed=1 at n≥2).
    """
    b = B(n_inputs=n, n_latches=1 + 4 * n)
    init = b.lats[0]
    x = b.lats[1 : 1 + n]
    y = b.lats[1 + n : 1 + 2 * n]
    i = b.lats[1 + 2 * n : 1 + 3 * n]
    seed = b.lats[1 + 3 * n : 1 + 4 * n]
    seed_in = list(b.ins)
    cont = _ult(b, i, _const(n, n))
    run = b.gAND(init, cont)
    y_shift = _shr1(y) if bug else _shl1(y)
    y1 = [b.gOR(y_shift[0], x[0])] + y_shift[1:]
    x1 = _shr1(x)
    i1 = _inc(b, i)
    b.set_next(init, TRUE_L)
    for j in range(n):
        b.set_next(x[j], b.gMUX(init, b.gMUX(run, x1[j], x[j]), seed_in[j]))
        b.set_next(y[j], b.gMUX(run, y1[j], y[j]))
        b.set_next(i[j], b.gMUX(run, i1[j], i[j]))
        b.set_next(seed[j], b.gMUX(init, seed[j], seed_in[j]))
    ref = list(reversed(seed))
    bad = b.gAND(b.gAND(init, b.gNOT(cont)), b.gNOT(_eq(b, y, ref)))
    return b.aag(bad), ("sat" if bug else "unsat"), f"bitrev n={n} bug={bug}"


# --- shift-add multiply: p = a*b ------------------------------------------


def circuit_mul_shiftadd(n: int, bug: bool) -> tuple[str, str, str]:
    """Shift-and-add multiply, n iterations, 2n-bit product.

    State: init, aw[2n] (widened a, shifted left each step), br[n],
    p[2n], i[n], a0[n], b0[n].
    Body: if br[0] (or always, in bug) p += aw; aw <<= 1; br >>= 1; i++.
    Bad after i==n: p ≠ ref(a0,b0).
    ok→UNSAT; bug→SAT (a=1,b=0 → p=2ⁿ−1≠0).
    """
    W = 2 * n
    b = B(n_inputs=2 * n, n_latches=1 + W + n + W + n + n + n)
    init = b.lats[0]
    off = 1
    aw = b.lats[off : off + W]
    off += W
    br = b.lats[off : off + n]
    off += n
    p = b.lats[off : off + W]
    off += W
    i = b.lats[off : off + n]
    off += n
    a0 = b.lats[off : off + n]
    off += n
    b0 = b.lats[off : off + n]
    off += n
    a_in, b_in = list(b.ins[:n]), list(b.ins[n:])
    cont = _ult(b, i, _const(n, n))
    run = b.gAND(init, cont)
    take = TRUE_L if bug else br[0]
    p_add, _ = _ripple_add(b, p, aw)
    p1 = _mux_word(b, take, p_add, p)
    aw1 = _shl1(aw)
    br1 = _shr1(br)
    i1 = _inc(b, i)
    b.set_next(init, TRUE_L)
    for j in range(W):
        load = a_in[j] if j < n else FALSE_L
        b.set_next(aw[j], b.gMUX(init, b.gMUX(run, aw1[j], aw[j]), load))
        b.set_next(p[j], b.gMUX(run, p1[j], p[j]))
    for j in range(n):
        b.set_next(br[j], b.gMUX(init, b.gMUX(run, br1[j], br[j]), b_in[j]))
        b.set_next(i[j], b.gMUX(run, i1[j], i[j]))
        b.set_next(a0[j], b.gMUX(init, a0[j], a_in[j]))
        b.set_next(b0[j], b.gMUX(init, b0[j], b_in[j]))
    # reference: combinational shift-add of a0,b0
    ref = _const(W, 0)
    sh = list(a0) + _const(n, 0)
    for k in range(n):
        ref_add, _ = _ripple_add(b, ref, sh)
        ref = _mux_word(b, b0[k], ref_add, ref)
        sh = _shl1(sh)
    done = b.gAND(init, b.gNOT(cont))
    bad = b.gAND(done, b.gNOT(_eq(b, p, ref)))
    return b.aag(bad), ("sat" if bug else "unsat"), f"mul_shiftadd n={n} bug={bug}"


# --- divmod: restoring division -------------------------------------------


def circuit_divmod(n: int, bug: bool) -> tuple[str, str, str]:
    """Restoring division: n iterations producing q,r with n = q·d + r.

    Precondition d≠0. ok asserts r < d. Bug asserts r ≤ d (i.e. checks
    only r ≤ d), which is *weaker* — so the assertion still holds and
    bug is also UNSAT? No: we want a SAT bug. Flip: bug *implements*
    the comparison wrong (uses `≥` instead of `>` when deciding to
    subtract), so r can equal d. ok→UNSAT, bug→SAT (e.g. n=d gives r=d).
    """
    b = B(n_inputs=2 * n, n_latches=1 + 4 * n + 2 * n)
    init = b.lats[0]
    off = 1
    r = b.lats[off : off + n]
    off += n
    q = b.lats[off : off + n]
    off += n
    i = b.lats[off : off + n]
    off += n
    d = b.lats[off : off + n]
    off += n
    n0 = b.lats[off : off + n]
    off += n
    work = b.lats[off : off + n]  # remaining dividend bits, MSB-first feed
    off += n
    n_in, d_in = list(b.ins[:n]), list(b.ins[n:])
    cont = _ult(b, i, _const(n, n))
    run = b.gAND(init, cont)
    # shift next dividend bit into r from work MSB
    r_sh = _shl1(r)
    r_sh = [b.gOR(r_sh[0], work[n - 1])] + r_sh[1:]  # wrong end? want MSB feed
    # Restoring division feeds dividend MSB→LSB. work holds remaining
    # bits MSB-aligned; each step takes work[n-1].
    r_in = r_sh
    sub, no_borrow = _ripple_sub(b, r_in, d)
    ge = no_borrow  # r_in ≥ d
    if bug:
        # use strict > instead of ≥: skip subtract when r_in == d
        gt = b.gAND(ge, b.gNOT(_eq(b, r_in, d)))
        take = gt
    else:
        take = ge
    r1 = _mux_word(b, take, sub, r_in)
    q1 = _shl1(q)
    q1 = [b.gOR(q1[0], take)] + q1[1:]
    work1 = _shl1(work)
    i1 = _inc(b, i)
    b.set_next(init, TRUE_L)
    for j in range(n):
        b.set_next(r[j], b.gMUX(run, r1[j], r[j]))
        b.set_next(q[j], b.gMUX(run, q1[j], q[j]))
        b.set_next(i[j], b.gMUX(run, i1[j], i[j]))
        b.set_next(d[j], b.gMUX(init, d[j], d_in[j]))
        b.set_next(n0[j], b.gMUX(init, n0[j], n_in[j]))
        b.set_next(work[j], b.gMUX(init, b.gMUX(run, work1[j], work[j]), n_in[j]))
    done = b.gAND(init, b.gNOT(cont))
    d_nz = b.gNOT(_is_zero(b, d))
    # property: r < d (assuming d≠0). bad = done ∧ d≠0 ∧ ¬(r<d)
    bad = b.gAND(b.gAND(done, d_nz), b.gNOT(_ult(b, r, d)))
    return b.aag(bad), ("sat" if bug else "unsat"), f"divmod n={n} bug={bug}"


# --- gcd: Euclid by repeated subtraction ----------------------------------


def circuit_gcd_sub(n: int, bug: bool) -> tuple[str, str, str]:
    """Subtractive Euclid: while a≠b { if a>b a-=b else b-=a }.

    Terminates with a==b==gcd when both inputs >0. Property checked:
    after termination, a divides a0 (encoded as a·k == a0 for some k —
    too costly). Use the simpler invariant a ≤ max(a0,b0) which the
    correct algorithm maintains and the bug violates.

    Bug: subtracts the *larger from the smaller* (swapped branches), so
    one operand underflows past 2ⁿ−1 > max(a0,b0). ok→UNSAT, bug→SAT.
    """
    b = B(n_inputs=2 * n, n_latches=1 + 4 * n)
    init = b.lats[0]
    off = 1
    a = b.lats[off : off + n]
    off += n
    bb = b.lats[off : off + n]
    off += n
    a0 = b.lats[off : off + n]
    off += n
    b0 = b.lats[off : off + n]
    a_in, b_in = list(b.ins[:n]), list(b.ins[n:])
    eq = _eq(b, a, bb)
    run = b.gAND(init, b.gNOT(eq))
    a_sub_b, _ = _ripple_sub(b, a, bb)
    b_sub_a, _ = _ripple_sub(b, bb, a)
    a_gt_b = _ult(b, bb, a)
    if bug:
        a1 = _mux_word(b, a_gt_b, a, a_sub_b)
        bb1 = _mux_word(b, a_gt_b, b_sub_a, bb)
    else:
        a1 = _mux_word(b, a_gt_b, a_sub_b, a)
        bb1 = _mux_word(b, a_gt_b, bb, b_sub_a)
    b.set_next(init, TRUE_L)
    for j in range(n):
        b.set_next(a[j], b.gMUX(init, b.gMUX(run, a1[j], a[j]), a_in[j]))
        b.set_next(bb[j], b.gMUX(init, b.gMUX(run, bb1[j], bb[j]), b_in[j]))
        b.set_next(a0[j], b.gMUX(init, a0[j], a_in[j]))
        b.set_next(b0[j], b.gMUX(init, b0[j], b_in[j]))
    nz0 = b.gAND(b.gNOT(_is_zero(b, a0)), b.gNOT(_is_zero(b, b0)))
    mx = _mux_word(b, _ult(b, a0, b0), b0, a0)
    # bad: precondition holds ∧ init done ∧ a > max(a0,b0)
    bad = b.gAND(b.gAND(init, nz0), _ult(b, mx, a))
    return b.aag(bad), ("sat" if bug else "unsat"), f"gcd_sub n={n} bug={bug}"


# --- running min over a stream --------------------------------------------


def circuit_stream_min(n: int, bug: bool) -> tuple[str, str, str]:
    """Track min of an input stream. Property: m ≤ every past input.

    Maintain m and the previous input prev. Bad: init ∧ m > prev.
    Bug: update uses `<` on the wrong side (m = x<m ? m : x), i.e.
    tracks *max* — violates m ≤ prev when stream decreases.
    ok→UNSAT, bug→SAT (after ≥2 inputs with x₁ < x₀).
    """
    b = B(n_inputs=n, n_latches=1 + 2 * n)
    init = b.lats[0]
    m = b.lats[1 : 1 + n]
    prev = b.lats[1 + n : 1 + 2 * n]
    x = list(b.ins)
    lt = _ult(b, x, m)
    if bug:
        m1 = _mux_word(b, lt, m, x)
    else:
        m1 = _mux_word(b, lt, x, m)
    b.set_next(init, TRUE_L)
    for j in range(n):
        b.set_next(m[j], b.gMUX(init, m1[j], x[j]))
        b.set_next(prev[j], x[j])
    bad = b.gAND(init, _ult(b, prev, m))
    return b.aag(bad), ("sat" if bug else "unsat"), f"stream_min n={n} bug={bug}"


# --- saturating counter ---------------------------------------------------


def circuit_sat_ctr(n: int, bug: bool) -> tuple[str, str, str]:
    """n-bit saturating up/down counter. Property: 0 ≤ c (trivial for
    unsigned) ∧ c ≤ 2ⁿ−1 (also trivial). Real property: after a
    decrement-at-zero, c stays 0.

    Bug: decrement is unconditional (no saturate-at-0), so c wraps to
    2ⁿ−1. Bad: c == 2ⁿ−1 ∧ just-decremented ∧ prev_c == 0.
    ok→UNSAT, bug→SAT (one step from reset with dec=1).
    """
    b = B(n_inputs=1, n_latches=1 + n + n + 1)
    dec = b.ins[0]
    init = b.lats[0]
    c = b.lats[1 : 1 + n]
    pc = b.lats[1 + n : 1 + 2 * n]
    pdec = b.lats[1 + 2 * n]
    c_inc = _inc(b, c)
    c_dec, _ = _ripple_sub(b, c, _const(n, 1))
    zero = _is_zero(b, c)
    full = b.all_and(c)
    if bug:
        c1 = _mux_word(b, dec, c_dec, _mux_word(b, full, c, c_inc))
    else:
        c1 = _mux_word(b, dec, _mux_word(b, zero, c, c_dec), _mux_word(b, full, c, c_inc))
    b.set_next(init, TRUE_L)
    b.set_next(pdec, dec)
    for j in range(n):
        b.set_next(c[j], c1[j])
        b.set_next(pc[j], c[j])
    bad = b.gAND(b.gAND(init, pdec), b.gAND(_is_zero(b, pc), b.all_and(c)))
    return b.aag(bad), ("sat" if bug else "unsat"), f"sat_ctr n={n} bug={bug}"


# --- clz (count leading zeros) --------------------------------------------


def circuit_clz(n: int, bug: bool) -> tuple[str, str, str]:
    """Iterative CLZ: while MSB(x)==0 ∧ x≠0 { x <<= 1; c++ }.

    Property after termination: seed==0 → c==n; else seed >> (n-1-c) has
    bit 0 set — i.e. c is the leading-zero count. Check via the simpler
    c ≤ n always; bug increments c past n (forgets the x≠0 guard, so
    seed=0 runs forever incrementing c, eventually c==n+1 if n+1<2ⁿ).
    ok→UNSAT, bug→SAT for n≥2 (needs c to reach n+1, so k≥n+2).
    """
    b = B(n_inputs=n, n_latches=1 + 2 * n + n)
    init = b.lats[0]
    x = b.lats[1 : 1 + n]
    c = b.lats[1 + n : 1 + 2 * n]
    seed = b.lats[1 + 2 * n : 1 + 3 * n]
    seed_in = list(b.ins)
    msb0 = b.gNOT(x[n - 1])
    nz = b.gNOT(_is_zero(b, x))
    if bug:
        cond = msb0
    else:
        cond = b.gAND(msb0, nz)
    run = b.gAND(init, cond)
    x1 = _shl1(x)
    c1 = _inc(b, c)
    b.set_next(init, TRUE_L)
    for j in range(n):
        b.set_next(x[j], b.gMUX(init, b.gMUX(run, x1[j], x[j]), seed_in[j]))
        b.set_next(c[j], b.gMUX(run, c1[j], c[j]))
        b.set_next(seed[j], b.gMUX(init, seed[j], seed_in[j]))
    bad = b.gAND(init, _ult(b, _const(n, n), c))
    return b.aag(bad), ("sat" if bug else "unsat"), f"clz n={n} bug={bug}"


# --- Fibonacci mod 2^n ----------------------------------------------------


def circuit_fib(n: int, bug: bool) -> tuple[str, str, str]:
    """Fibonacci pair (a,b) with a'=b, b'=a+b. Property: a ≤ b always
    (true for non-negative Fibonacci until b wraps; restrict to first
    n steps so no wrap). Guard with step counter i<n.

    Bug: starts with a=1,b=0 (swapped), giving a>b at step 0.
    ok→UNSAT (for k≤n), bug→SAT (immediately).
    """
    b = B(n_inputs=0, n_latches=3 * n)
    a = b.lats[:n]
    bb = b.lats[n : 2 * n]
    i = b.lats[2 * n : 3 * n]
    s, _ = _ripple_add(b, a, bb)
    cont = _ult(b, i, _const(n, n))
    i1 = _inc(b, i)
    for j in range(n):
        b.set_next(a[j], b.gMUX(cont, bb[j], a[j]), reset=(1 if (bug and j == 0) else 0))
        b.set_next(bb[j], b.gMUX(cont, s[j], bb[j]), reset=(0 if bug else (1 if j == 0 else 0)))
        b.set_next(i[j], b.gMUX(cont, i1[j], i[j]))
    bad = b.gAND(cont, _ult(b, bb, a))
    return b.aag(bad), ("sat" if bug else "unsat"), f"fib n={n} bug={bug}"


# --- binary search bounds -------------------------------------------------


def circuit_token_bucket(n: int, bug: bool) -> tuple[str, str, str]:
    """Token bucket: each step add 1 token (cap 2ⁿ−1), consume `take`
    (nondet 0/1). Property: tokens never exceed cap.

    Bug: add-then-cap is implemented as cap-then-add (so a full bucket
    overflows to 0 and the *next* add makes it 1, but the overflow step
    itself wraps tokens past cap). Concretely: bug computes
    tokens' = (tokens+1) without the saturate mux. ok→UNSAT, bug→SAT
    (after 2ⁿ−1 steps with take=0, tokens wraps; bad fires when
    prev_tokens=cap ∧ tokens=0 — actually we want tokens>cap which
    can't happen in n bits). Change bad to: tokens < prev_tokens ∧
    take=0 (a non-consume step *decreased* tokens — impossible if
    saturating, possible on wrap).
    """
    b = B(n_inputs=1, n_latches=1 + 2 * n + 1)
    take = b.ins[0]
    init = b.lats[0]
    tok = b.lats[1 : 1 + n]
    ptok = b.lats[1 + n : 1 + 2 * n]
    ptake = b.lats[1 + 2 * n]
    full = b.all_and(tok)
    inc = _inc(b, tok)
    after_add = inc if bug else _mux_word(b, full, tok, inc)
    dec, _ = _ripple_sub(b, after_add, _const(n, 1))
    nz = b.gNOT(_is_zero(b, after_add))
    after_take = _mux_word(b, b.gAND(take, nz), dec, after_add)
    b.set_next(init, TRUE_L)
    b.set_next(ptake, take)
    for j in range(n):
        b.set_next(tok[j], after_take[j])
        b.set_next(ptok[j], tok[j])
    bad = b.gAND(b.gAND(init, b.gNOT(ptake)), _ult(b, tok, ptok))
    return b.aag(bad), ("sat" if bug else "unsat"), f"token_bucket n={n} bug={bug}"


# --- one-hot encoder roundtrip --------------------------------------------


def circuit_onehot_rt(n: int, bug: bool) -> tuple[str, str, str]:
    """Encode i∈[0,n) to one-hot h, decode back to j; property j==i.

    Loop increments i each step (mod n via reset at i==n). Bug: decoder
    priority is reversed (returns highest set bit index, but encoder
    sets lowest — same thing for true one-hot, so we instead bug the
    encoder to also set bit 0 always, breaking the roundtrip for i>0).
    ok→UNSAT, bug→SAT (i=1 → h=0b11 → decode→0≠1).
    """
    m = max(2, (n - 1).bit_length())
    b = B(n_inputs=0, n_latches=m)
    i = list(b.lats[:m])
    i1 = _inc(b, i)
    wrap = _eq(b, i, _const(m, n - 1))
    for j in range(m):
        b.set_next(i[j], b.gMUX(wrap, FALSE_L, i1[j]))
    # one-hot encode (combinational)
    h = [_eq(b, i, _const(m, k)) for k in range(n)]
    if bug:
        h[0] = TRUE_L
    # decode: lowest-set index
    dec = _const(m, 0)
    found = FALSE_L
    for k in range(n):
        pick = b.gAND(h[k], b.gNOT(found))
        dec = _mux_word(b, pick, _const(m, k), dec)
        found = b.gOR(found, h[k])
    bad = b.gNOT(_eq(b, dec, i))
    return b.aag(bad), ("sat" if bug else "unsat"), f"onehot_rt n={n} bug={bug}"


# --- registry -------------------------------------------------------------

CircuitFn = Callable[[int, bool], tuple[str, str, str]]

REGISTRY_CBMC: dict[str, CircuitFn] = {
    "popcount": circuit_popcount,
    "parity": circuit_parity,
    "bitrev": circuit_bitrev,
    "mul_shiftadd": circuit_mul_shiftadd,
    "divmod": circuit_divmod,
    "gcd_sub": circuit_gcd_sub,
    "stream_min": circuit_stream_min,
    "sat_ctr": circuit_sat_ctr,
    "clz": circuit_clz,
    "fib": circuit_fib,
    "token_bucket": circuit_token_bucket,
    "onehot_rt": circuit_onehot_rt,
}

# BMC bound at which each `_bug` variant's bad signal is provably
# reachable (step 0 = reset, step 1 = init/load for circuits that latch
# nondet inputs). Verified by `test_bug_depth_reachable`. This is a
# sufficient bound, not a tight one — at smaller k the answer is left
# as "unknown" rather than analytically claimed UNSAT.
BUG_DEPTH: dict[str, Callable[[int], int]] = {
    "popcount": lambda n: 1 + n,
    "parity": lambda n: 1,
    "bitrev": lambda n: 1 + n,
    "mul_shiftadd": lambda n: 1 + n,
    "divmod": lambda n: 1 + n,
    "gcd_sub": lambda n: 2,
    "stream_min": lambda n: 2,
    "sat_ctr": lambda n: 1,
    "clz": lambda n: 2 + n,
    "fib": lambda n: 0,
    "token_bucket": lambda n: 1 << n,
    "onehot_rt": lambda n: 1,
}


def expected_at(name: str, n: int, bug: bool, k: int) -> str:
    """Analytically-derived BMC reachability verdict at bound k.

    `_ok` is correct by construction → unsat at every k. `_bug` is sat
    at k ≥ BUG_DEPTH(n) (test-verified); at smaller k we don't claim
    either way.
    """
    if not bug:
        return "unsat"
    return "sat" if k >= BUG_DEPTH[name](n) else "unknown"
