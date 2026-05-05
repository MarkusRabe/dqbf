"""Fault-injected variants of the safe `bmc2dqbf.circuits` for the
inductive-invariant encoding.

The original mutex / fifo1 / alu_add are correct (bad unreachable), so
their indinv encoding is SAT. These variants break one transition so
bad becomes reachable, hence no inductive invariant exists ⇒ UNSAT.
"""

from __future__ import annotations

from collections.abc import Callable

from tools.bmc2dqbf.circuits import FALSE_L, B


def circuit_mutex_buggy(n: int) -> tuple[str, str]:
    """As `circuit_mutex` but grant[1] ignores priority — req[0]=req[1]=1
    yields two simultaneous grants on the next cycle."""
    b = B(n_inputs=n, n_latches=n)
    higher = FALSE_L
    for k in range(n):
        if k == 1:
            nxt = b.ins[1]
        elif k == 0:
            nxt = b.ins[0]
        else:
            nxt = b.gAND(b.ins[k], b.gNOT(higher))
        b.set_next(b.lats[k], nxt)
        higher = b.gOR(higher, b.ins[k]) if k else b.ins[0]
    pairs = [b.gAND(b.lats[i], b.lats[j]) for i in range(n) for j in range(i + 1, n)]
    bad = b.any_or(pairs)
    return b.aag(bad), f"mutex_buggy n={n}: grant[1] ignores priority"


def circuit_fifo1_buggy(n: int) -> tuple[str, str]:
    """As `circuit_fifo1` but the shadow inverts data bit 0 on write —
    first write makes r[0] ≠ sd[0]."""
    b = B(n_inputs=1 + n, n_latches=2 * n)
    we, d = b.ins[0], b.ins[1:]
    r, sd = b.lats[:n], b.lats[n:]
    for k in range(n):
        b.set_next(r[k], b.gMUX(we, d[k], r[k]))
        src = b.gNOT(d[k]) if k == 0 else d[k]
        b.set_next(sd[k], b.gMUX(we, src, sd[k]))
    diffs = [b.gXOR(r[k], sd[k]) for k in range(n)]
    bad = b.any_or(diffs)
    return b.aag(bad), f"fifo1_buggy n={n}: shadow inverts d[0]"


def circuit_alu_add_buggy(n: int) -> tuple[str, str]:
    """As `circuit_alu_add` but the pipelined sum drops c[0] — bit 0 of
    `out` is just `a[0]`, so `out ≠ ref` whenever `c[0]=1`."""
    b = B(n_inputs=2 * n, n_latches=3 * n)
    a, c = b.ins[:n], b.ins[n:]
    out, sa, sc = b.lats[:n], b.lats[n : 2 * n], b.lats[2 * n :]
    carry = FALSE_L
    for k in range(n):
        s = a[k] if k == 0 else b.gXOR(b.gXOR(a[k], c[k]), carry)
        carry = b.gOR(b.gAND(a[k], c[k]), b.gAND(carry, b.gXOR(a[k], c[k])))
        b.set_next(out[k], s)
        b.set_next(sa[k], a[k])
        b.set_next(sc[k], c[k])
    carry2 = FALSE_L
    diffs: list[int] = []
    for k in range(n):
        s2 = b.gXOR(b.gXOR(sa[k], sc[k]), carry2)
        carry2 = b.gOR(b.gAND(sa[k], sc[k]), b.gAND(carry2, b.gXOR(sa[k], sc[k])))
        diffs.append(b.gXOR(out[k], s2))
    bad = b.any_or(diffs)
    return b.aag(bad), f"alu_add_buggy n={n}: out[0] drops c[0]"


REGISTRY_BUGGY: dict[str, Callable[[int], tuple[str, str]]] = {
    "mutex_buggy": circuit_mutex_buggy,
    "fifo1_buggy": circuit_fifo1_buggy,
    "alu_add_buggy": circuit_alu_add_buggy,
}
