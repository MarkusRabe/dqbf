"""Instance generators for the multi-learn experiment.

Each generator returns ``(n_vars, clauses)``. Most are UNSAT — the
question is how the solver *proves* UNSAT, not whether. The classes are
chosen to span the structure spectrum:

- Structured, ER-helps: XOR chains, equality chains, adder/multiplier
  miters. These have small circuit cones and exponentially many cut
  clauses; extension variables compress them.
- Structured, ER-neutral: pigeonhole. Symmetric but no useful gate
  structure to introduce extensions for (though symmetry breaking helps).
- Cardinality: at-most-k vs at-least-k+1. PB constraints compress these
  exponentially over clauses; ER subsumes PB.
- Unstructured: random 3-SAT. The cone is whatever it is; no structure
  to exploit. Multi-learn should hurt.
"""

from __future__ import annotations

import random
from collections.abc import Iterator

Lit = int
Clause = tuple[Lit, ...]


class _VarPool:
    def __init__(self, start: int = 0) -> None:
        self.n = start

    def new(self) -> int:
        self.n += 1
        return self.n


# ───────────────────────── XOR chains ─────────────────────────


def tseitin_xor_chain(n: int) -> tuple[int, list[Clause]]:
    """``x₁ ⊕ x₂ ⊕ … ⊕ xₙ = 1`` and ``= 0`` Tseitin'd. UNSAT.

    A textbook ER-helps instance: any resolution proof has ``2^Ω(n)``
    clauses, but with ``n`` extension variables (the chain prefixes) the
    proof is linear.
    """
    p = _VarPool()
    xs = [p.new() for _ in range(n)]
    cls: list[Clause] = []

    def chain(target: int) -> None:
        prev = xs[0]
        for x in xs[1:]:
            z = p.new()
            # z = prev ⊕ x
            cls.extend(
                [(-z, prev, x), (-z, -prev, -x), (z, -prev, x), (z, prev, -x)]
            )
            prev = x  # NOTE: bug? we should accumulate via z, not x
            prev = z
        cls.append((prev,) if target == 1 else (-prev,))

    chain(1)
    chain(0)
    return p.n, cls


def parity_tree(n: int, parity: int = 1) -> tuple[int, list[Clause]]:
    """``⊕ x₁..xₙ = parity`` as a balanced Tseitin tree, plus a unit
    asserting one of the leaves both ways. UNSAT for any parity."""
    p = _VarPool()
    xs = [p.new() for _ in range(n)]
    cls: list[Clause] = []

    def reduce(lits: list[int]) -> int:
        while len(lits) > 1:
            nxt: list[int] = []
            for i in range(0, len(lits) - 1, 2):
                a, b = lits[i], lits[i + 1]
                z = p.new()
                cls.extend(
                    [(-z, a, b), (-z, -a, -b), (z, -a, b), (z, a, -b)]
                )
                nxt.append(z)
            if len(lits) % 2:
                nxt.append(lits[-1])
            lits = nxt
        return lits[0]

    out = reduce(list(xs))
    cls.append((out,) if parity else (-out,))
    # contradict it: pick a leaf and force it both ways via a second tree
    out2 = reduce(list(xs))
    cls.append((out2,) if 1 - parity else (-out2,))
    return p.n, cls


# ───────────────────────── equality chains ─────────────────────────


def equality_chain(n: int) -> tuple[int, list[Clause]]:
    """``a₁ ↔ a₂ ↔ … ↔ aₙ`` plus ``a₁ ⊕ aₙ``. UNSAT."""
    p = _VarPool()
    xs = [p.new() for _ in range(n)]
    cls: list[Clause] = []
    for a, b in zip(xs, xs[1:]):
        cls.extend([(a, -b), (-a, b)])
    cls.extend([(xs[0], xs[-1]), (-xs[0], -xs[-1])])
    return p.n, cls


def equality_grid(rows: int, cols: int) -> tuple[int, list[Clause]]:
    """A grid of variables where each cell equals its right and down
    neighbor; force two corners to differ. UNSAT, with much wider cones
    than a chain (more independent paths through the conflict graph)."""
    p = _VarPool()
    g = [[p.new() for _ in range(cols)] for _ in range(rows)]
    cls: list[Clause] = []
    for r in range(rows):
        for c in range(cols):
            if c + 1 < cols:
                a, b = g[r][c], g[r][c + 1]
                cls.extend([(a, -b), (-a, b)])
            if r + 1 < rows:
                a, b = g[r][c], g[r + 1][c]
                cls.extend([(a, -b), (-a, b)])
    a, b = g[0][0], g[rows - 1][cols - 1]
    cls.extend([(a, b), (-a, -b)])
    return p.n, cls


# ───────────────────────── arithmetic ─────────────────────────


def _xor3(p: _VarPool, cls: list[Clause], a: int, b: int, c: int) -> int:
    """3-input XOR (full-adder sum bit)."""
    ab = p.new()
    cls.extend([(-ab, a, b), (-ab, -a, -b), (ab, -a, b), (ab, a, -b)])
    s = p.new()
    cls.extend([(-s, ab, c), (-s, -ab, -c), (s, -ab, c), (s, ab, -c)])
    return s


def _maj3(p: _VarPool, cls: list[Clause], a: int, b: int, c: int) -> int:
    """3-input majority (full-adder carry bit)."""
    m = p.new()
    cls.extend(
        [
            (-m, a, b),
            (-m, a, c),
            (-m, b, c),
            (m, -a, -b),
            (m, -a, -c),
            (m, -b, -c),
        ]
    )
    return m


def _and(p: _VarPool, cls: list[Clause], a: int, b: int) -> int:
    z = p.new()
    cls.extend([(-z, a), (-z, b), (z, -a, -b)])
    return z


def adder_miter(width: int) -> tuple[int, list[Clause]]:
    """Two ripple-carry adders for the same inputs; assert one output bit
    differs. UNSAT — and the conflict cones are XOR/MAJ chains."""
    p = _VarPool()
    a = [p.new() for _ in range(width)]
    b = [p.new() for _ in range(width)]
    cls: list[Clause] = []

    def ripple() -> list[int]:
        c = p.new()
        cls.append((-c,))  # carry-in = 0
        out: list[int] = []
        for i in range(width):
            s = _xor3(p, cls, a[i], b[i], c)
            c = _maj3(p, cls, a[i], b[i], c)
            out.append(s)
        out.append(c)
        return out

    s1, s2 = ripple(), ripple()
    # assert at least one bit differs (the miter)
    diffs = []
    for x, y in zip(s1, s2):
        d = p.new()
        cls.extend([(-d, x, y), (-d, -x, -y), (d, -x, y), (d, x, -y)])
        diffs.append(d)
    cls.append(tuple(diffs))
    return p.n, cls


def multiplier_miter(width: int) -> tuple[int, list[Clause]]:
    """Two array multipliers for the same inputs; assert outputs differ.
    UNSAT, and the cones mix AND-gates (partial products) with XOR/MAJ
    (the addition tree). The hardest of the structured classes."""
    p = _VarPool()
    a = [p.new() for _ in range(width)]
    b = [p.new() for _ in range(width)]
    cls: list[Clause] = []

    def mult() -> list[int]:
        # partial products
        pp = [[_and(p, cls, a[i], b[j]) for j in range(width)] for i in range(width)]
        # diagonal additions
        out: list[int] = [0] * (2 * width)
        carry = p.new()
        cls.append((-carry,))
        col_sum: list[int] = []
        for k in range(2 * width - 1):
            terms = [pp[i][k - i] for i in range(width) if 0 <= k - i < width]
            # reduce via full adders (carry-save would be better; this is
            # readable, not fast)
            carries: list[int] = []
            while len(terms) >= 3:
                x, y, z = terms[:3]
                terms = terms[3:]
                terms.append(_xor3(p, cls, x, y, z))
                carries.append(_maj3(p, cls, x, y, z))
            while len(terms) >= 2:
                x, y = terms[:2]
                terms = terms[2:]
                s = p.new()
                cls.extend([(-s, x, y), (-s, -x, -y), (s, -x, y), (s, x, -y)])
                terms.append(s)
                carries.append(_and(p, cls, x, y))
            col_sum.append(terms[0] if terms else _const_false(p, cls))
            # push carries to the next column
            terms = carries
            # for simplicity, fold the carries from this column into the next
            for c in carries:
                pp_next = pp  # carries become new "partial products" for col k+1
            # Simpler approach: just append carries to the next column's pp
            if carries and k + 1 < 2 * width:
                for c in carries:
                    # extend pp with a synthetic row (ugly but correct)
                    pass
            # NB: the above carry handling is wrong; use a simpler scheme:
        return col_sum

    # the multiplier above has subtle carry-bug potential; for the
    # *experiment* we don't need a correct multiplier, we need a
    # CNF whose cones look like AND/XOR/MAJ trees. Use a simpler scheme:
    return _multiplier_simple(width)


def _const_false(p: _VarPool, cls: list[Clause]) -> int:
    z = p.new()
    cls.append((-z,))
    return z


def _multiplier_simple(width: int) -> tuple[int, list[Clause]]:
    """Simpler & correct: shift-and-add multiplier. Two copies, miter."""
    p = _VarPool()
    a = [p.new() for _ in range(width)]
    b = [p.new() for _ in range(width)]
    cls: list[Clause] = []

    def mult() -> list[int]:
        acc = [_const_false(p, cls) for _ in range(2 * width)]
        for i in range(width):
            # row_i = a if b[i] else 0, shifted by i
            row = [_and(p, cls, a[j], b[i]) for j in range(width)]
            # acc += row << i  (ripple)
            c = _const_false(p, cls)
            for j in range(width):
                pos = i + j
                s = _xor3(p, cls, acc[pos], row[j], c)
                c = _maj3(p, cls, acc[pos], row[j], c)
                acc[pos] = s
            # propagate final carry
            pos = i + width
            while pos < 2 * width and c is not None:
                s = p.new()
                cls.extend([(-s, acc[pos], c), (-s, -acc[pos], -c), (s, -acc[pos], c), (s, acc[pos], -c)])
                nc = _and(p, cls, acc[pos], c)
                acc[pos] = s
                c = nc
                pos += 1
        return acc

    p1, p2 = mult(), mult()
    diffs = []
    for x, y in zip(p1, p2):
        d = p.new()
        cls.extend([(-d, x, y), (-d, -x, -y), (d, -x, y), (d, x, -y)])
        diffs.append(d)
    cls.append(tuple(diffs))
    return p.n, cls


# ───────────────────────── pigeonhole ─────────────────────────


def php(n: int) -> tuple[int, list[Clause]]:
    """``n+1`` pigeons into ``n`` holes. UNSAT. Variables ``p_{i,j}``
    indexed ``(i-1)*n + j`` for ``1 ≤ i ≤ n+1, 1 ≤ j ≤ n``."""
    var = lambda i, j: (i - 1) * n + j
    cls: list[Clause] = []
    # each pigeon in some hole
    for i in range(1, n + 2):
        cls.append(tuple(var(i, j) for j in range(1, n + 1)))
    # no two pigeons in the same hole
    for j in range(1, n + 1):
        for i1 in range(1, n + 2):
            for i2 in range(i1 + 1, n + 2):
                cls.append((-var(i1, j), -var(i2, j)))
    return (n + 1) * n, cls


# ───────────────────────── cardinality ─────────────────────────


def at_most_k_vs_at_least(n: int, k: int) -> tuple[int, list[Clause]]:
    """Sequential encoding (Sinz 2005) of ``Σxᵢ ≤ k`` plus a PHP-style
    encoding of ``Σxᵢ ≥ k+1``. UNSAT. The cone of an at-most violation
    is a chain of "running sum" auxiliary variables — a cardinality
    structure that PB constraints (and ER) compress exponentially over
    clauses.

    The at-least side is encoded so that the conflict isn't trivially
    found at level 0: instead of pinning ``k+1`` of the ``xᵢ`` true with
    units, we use ``k+1`` "placement" indicator vars ``yⱼ`` each forced
    to point at a distinct true ``xᵢ``. The solver has to *discover*
    which ``xᵢ`` are true — the cone then traverses the running-sum
    chain.
    """
    p = _VarPool()
    xs = [p.new() for _ in range(n)]  # x_1..x_n
    cls: list[Clause] = []
    # Sinz: s[i][j] = "at least j of x_1..x_i"; 1 ≤ i ≤ n-1, 1 ≤ j ≤ k.
    s = [[0] * (k + 1) for _ in range(n)]  # 1-indexed
    for i in range(1, n):
        for j in range(1, k + 1):
            s[i][j] = p.new()
    cls.append((-xs[0], s[1][1]))
    for j in range(2, k + 1):
        cls.append((-s[1][j],))
    for i in range(2, n):
        cls.append((-xs[i - 1], s[i][1]))
        cls.append((-s[i - 1][1], s[i][1]))
        for j in range(2, k + 1):
            cls.append((-xs[i - 1], -s[i - 1][j - 1], s[i][j]))
            cls.append((-s[i - 1][j], s[i][j]))
    for i in range(2, n + 1):
        cls.append((-xs[i - 1], -s[i - 1][k]))

    # Σxᵢ ≥ k+1 by sequential at-least over the *reversed* sequence:
    # t[i][j] = "at least j of x_i..x_n", with t[1][k+1] forced true.
    # This keeps the cone shape symmetric: both directions traverse a
    # running-sum chain.
    K = k + 1
    t = [[0] * (K + 1) for _ in range(n + 2)]
    for i in range(1, n + 1):
        for j in range(1, K + 1):
            t[i][j] = p.new()
    # base: t[n][1] ← x_n;  t[n][j] = ⊥ for j>1
    cls.append((-t[n][1], xs[n - 1]))
    for j in range(2, K + 1):
        cls.append((-t[n][j],))
    # t[i][j] ← (t[i+1][j]) ∨ (x_i ∧ t[i+1][j-1])
    for i in range(n - 1, 0, -1):
        for j in range(1, K + 1):
            # t[i][j] → t[i+1][j] ∨ x_i
            cls.append((-t[i][j], t[i + 1][j], xs[i - 1]))
            # t[i][j] ∧ ¬t[i+1][j] → t[i+1][j-1]
            if j > 1:
                cls.append((-t[i][j], t[i + 1][j], t[i + 1][j - 1]))
    cls.append((t[1][K],))
    return p.n, cls


# ───────────────────────── random 3-SAT ─────────────────────────


def random_3sat(n: int, ratio: float = 4.26, seed: int = 0) -> tuple[int, list[Clause]]:
    """Random 3-SAT at the phase transition. The unstructured baseline."""
    rng = random.Random(seed)
    m = int(n * ratio)
    cls: list[Clause] = []
    for _ in range(m):
        vs = rng.sample(range(1, n + 1), 3)
        cls.append(tuple(v if rng.random() < 0.5 else -v for v in vs))
    return n, cls


# ───────────────────────── registry ─────────────────────────


GENERATORS: dict[str, list[tuple[str, tuple[int, list[Clause]]]]] = {}


def all_instances() -> Iterator[tuple[str, str, int, list[Clause]]]:
    """Yield ``(class, name, n_vars, clauses)`` over the experiment suite.
    Sizes are tuned for a Python CDCL: hundreds of conflicts, not millions."""
    for n in (4, 6, 8, 10):
        yield "xor_chain", f"xor_chain_n{n}", *tseitin_xor_chain(n)
    for n in (4, 6, 8):
        yield "parity_tree", f"parity_tree_n{n}", *parity_tree(n)
    for n in (8, 16, 24, 32):
        yield "eq_chain", f"eq_chain_n{n}", *equality_chain(n)
    for r, c in ((3, 3), (4, 4), (5, 5)):
        yield "eq_grid", f"eq_grid_{r}x{c}", *equality_grid(r, c)
    for w in (2, 3, 4):
        yield "adder", f"adder_w{w}", *adder_miter(w)
    for w in (2, 3):
        yield "multiplier", f"multiplier_w{w}", *_multiplier_simple(w)
    for n in (3, 4, 5):
        yield "php", f"php_n{n}", *php(n)
    for n, k in ((10, 3), (12, 4), (16, 5)):
        yield "card", f"card_n{n}_k{k}", *at_most_k_vs_at_least(n, k)
    for n, seed in ((40, 1), (50, 2), (60, 3), (40, 7), (50, 8)):
        nv, cls = random_3sat(n, seed=seed)
        yield "random3sat", f"r3sat_n{n}_s{seed}", nv, cls
