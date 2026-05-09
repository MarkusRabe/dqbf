"""Conflict-cone analysis: cuts, structure detection, prime implicates.

Three views of the same object:

1. **Cuts** — every reason-side/conflict-side partition of the cone DAG
   yields a valid learned clause. The 1-UIP is one. We enumerate (a
   bounded number of) the others to see how many *distinct, mutually
   non-subsuming* clauses one conflict admits.

2. **Structure** — does the cone look like an XOR chain, an equality
   chain, a cardinality constraint, or unstructured CNF? Structured
   cones admit a *single* learned object (a parity constraint, a PB
   constraint, an extension definition) that subsumes exponentially many
   clauses. That's the "don't enumerate; generalize" payoff.

3. **Prime implicates** — for tiny cones we compute the exact set of
   strongest learnable clauses by truth-table enumeration. The count of
   prime implicates is the ground truth for "how much a clause-only
   learner is throwing away."

The cone is the *circuit*. The 1-UIP clause is a one-bit projection of
it. The point of this module is to put numbers on what's lost.
"""

from __future__ import annotations

import itertools
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from cdcl import Clause, ConflictCone, Lit


# ───────────────────────── cut enumeration ─────────────────────────


def all_uip_cuts(cone: ConflictCone) -> list[tuple[Lit, Clause]]:
    """Every UIP at the current level, in trail order (last-assigned
    first), each with its learned clause.

    The trail-order resolution sweep visits a sequence of clauses; each
    time exactly one current-level literal remains it's a UIP. The 1-UIP
    is the first such point, the decision literal is the last.
    """
    out: list[tuple[Lit, Clause]] = []
    learned: set[Lit] = set()
    seen: set[int] = set()
    pending: list[Lit] = []  # current-level lits in `learned`, latest first
    pos = {l: i for i, l in enumerate(cone.trail_order)}
    root_vars = {abs(l) for l in cone.roots}

    def add(lit: Lit) -> None:
        v = abs(lit)
        if v in seen or v in root_vars:
            return
        seen.add(v)
        # trail literal whose negation is `lit`
        t = -lit
        if t in pos:
            pending.append(t)
        else:
            learned.add(lit)

    for l in cone.conflict_clause:
        add(l)
    pending.sort(key=lambda t: pos[t])  # ascending trail order; pop from end

    while pending:
        if len(pending) == 1:
            uip = pending[0]
            cl = tuple(sorted({*learned, -uip}, key=abs))
            out.append((uip, cl))
        t = pending.pop()  # latest-assigned
        if t == cone.decision:
            break
        rc = cone.reasons.get(t)
        if rc is None:
            break
        for m in rc:
            if m != t:
                add(m)
        pending.sort(key=lambda t: pos[t])
    return out


def enumerate_cuts(cone: ConflictCone, *, cap: int = 64) -> list[Clause]:
    """Bounded enumeration of distinct learnable clauses.

    Walk the resolution lattice: from the conflicting clause, repeatedly
    pick *one* current-level implied literal to resolve away. Each
    intermediate clause is a valid learned clause (it's a cut). Distinct
    ones (up to subsumption) are collected, capped at ``cap``.

    Root-level (level-0) literals are dropped from every cut — they're
    permanently false, so keeping them only bloats the clause without
    changing its meaning. (Real CDCL implementations do this too.)

    The lattice can be exponential — a wide cone where many literals are
    independently implied admits 2^k stop points. The cap keeps this
    cheap; what we want is the *count*, not the full set.
    """
    root_neg = frozenset(-l for l in cone.roots)
    seen: set[Clause] = set()
    out: list[Clause] = []
    init = frozenset(l for l in cone.conflict_clause if l not in root_neg)
    queue: deque[frozenset[Lit]] = deque([init])
    visited: set[frozenset[Lit]] = {init}

    while queue and len(seen) < cap:
        cl = queue.popleft()
        resolvable = [t for t in cone.reasons if -t in cl]
        norm = tuple(sorted(cl, key=abs))
        if norm not in seen:
            seen.add(norm)
            out.append(norm)
        for t in resolvable:
            rc = cone.reasons[t]
            new = (cl - {-t}) | {m for m in rc if m != t and m not in root_neg}
            if any(-l in new for l in new):  # tautology
                continue
            if new not in visited:
                visited.add(new)
                queue.append(new)
    return out


def filter_subsumed(clauses: Sequence[Clause]) -> list[Clause]:
    """Drop clauses subsumed by a strictly shorter one in the list."""
    cs = sorted(set(clauses), key=len)
    out: list[Clause] = []
    sets: list[frozenset[Lit]] = []
    for c in cs:
        fc = frozenset(c)
        if any(s <= fc for s in sets):
            continue
        out.append(c)
        sets.append(fc)
    return out


# ───────────────────────── structure classifier ─────────────────────────


@dataclass
class ConeShape:
    """Structural fingerprint of a conflict cone.

    The classification is a *prediction* of how many distinct learnable
    clauses the cone admits and what compact summary, if any, captures
    them. Features (width, depth, sharing) capture the shape of the
    implication DAG; ``kind`` is a heuristic label for the dominant
    clause pattern.
    """

    kind: str  # "xor" | "eq" | "card" | "and_or" | "unstructured"
    width: int  # # of independently-implied current-level lits (DAG sources)
    depth: int  # longest reason chain
    sharing: int  # # of cone lits reachable via >1 path
    detail: str = ""


def classify_cone(cone: ConflictCone) -> ConeShape:
    """Classify by clause-width histogram and DAG topology.

    The clause-width signature is the cheapest predictor of the cone's
    proof-theoretic class:

    - **all ternary** with chained variable triples → XOR (Tseitin parity
      gates produce only ternary clauses; a cone of them is a parity
      chain). Resolution proofs of XOR are exponential; ER proofs are
      linear; this is the class where a richer learned object pays off
      most.
    - **all binary** → equality / implication chain. The cone is a path
      in the implication graph; cuts = chain length; each cut clause is
      ``(¬a₁ ∨ aᵢ)`` for some prefix. Learning a single equality clause
      ``a₁ ↔ aₙ`` (two binaries via one extension var, or just both
      directions) subsumes the whole chain.
    - **binary-dominated with a few wide** → cardinality. The at-most
      chain is binary; the at-least clause is wide. PB/cardinality
      constraints (and ER) compress this exponentially.
    - **mostly clauses with one polarity** → AND/OR cone (adder carry,
      multiplier partial-product). Conjunctions and disjunctions have a
      polarity skew; the cone is a small monotone circuit.
    - else → unstructured.

    The DAG-topology features (width, depth, sharing) are independent
    predictors of *how many* cuts there are: wide shallow cones admit
    exponentially many; narrow deep cones admit linearly many.
    """
    cls = cone.cone_clauses
    width, depth, sharing = _cone_topology(cone)
    if not cls:
        return ConeShape("unstructured", width, depth, sharing, "empty cone")

    lengths = [len(c) for c in cls]
    n2 = sum(1 for l in lengths if l == 2)
    n3 = sum(1 for l in lengths if l == 3)
    nw = sum(1 for l in lengths if l > 3)
    n = len(lengths)

    # --- XOR: predominantly ternary, no wide clauses, chained vars.
    if n3 >= 0.8 * n and nw == 0 and n >= 2:
        if _vars_chain(cls):
            return ConeShape("xor", width, depth, sharing, f"{n3}/{n} ternary chain")

    # --- equality / implication chain: all binary.
    if n2 == n and n >= 2:
        return ConeShape("eq", width, depth, sharing, f"{n} binary chain")

    # --- cardinality: binary-dominated, ≤1 wide clause.
    if n2 >= 0.6 * n and nw <= 1 and n >= 3:
        return ConeShape("card", width, depth, sharing, f"{n2}/{n} binary + {nw} wide")

    # --- AND/OR cone: strong polarity skew.
    pos = sum(1 for c in cls for l in c if l > 0)
    neg = sum(1 for c in cls for l in c if l < 0)
    if (pos + neg) > 0 and max(pos, neg) / (pos + neg) > 0.75:
        return ConeShape("and_or", width, depth, sharing, f"polarity skew {max(pos,neg)/(pos+neg):.2f}")

    return ConeShape("unstructured", width, depth, sharing)


def _cone_topology(cone: ConflictCone) -> tuple[int, int, int]:
    """(width, depth, sharing) of the current-level reason DAG.

    width = the widest antichain in the cone DAG, computed as the peak
            ``path_count`` during a 1-UIP-style trail-order sweep. This
            is the number of *independently true* current-level literals
            that the conflict graph can have on the conflict side at any
            cut — a lower bound on the number of mutually-incomparable
            UIP-style cuts. Width 1 means the cone is a chain; high
            width means the conflict graph fans out and admits many cuts.
    depth = longest reason chain (max trail-order distance from decision
            to a cone literal).
    sharing = # of cone literals with >1 cone-internal successor (DAG
            joins). Sharing means the same sub-derivation is reused —
            exactly the case where an extension variable for it pays off.
    """
    cur = cone.current_level_lits
    pos = {l: i for i, l in enumerate(cone.trail_order)}
    succ: dict[Lit, set[Lit]] = {l: set() for l in cur}
    pred: dict[Lit, set[Lit]] = {l: set() for l in cur}
    for l, rc in cone.reasons.items():
        for m in rc:
            if m == l:
                continue
            tm = -m
            if tm in cur:
                pred[l].add(tm)
                succ[tm].add(l)
    sharing = sum(1 for l in cur if len(succ[l]) > 1)

    # Width = peak path_count in a trail-order sweep starting from the
    # conflicting clause's current-level seeds.
    seen: set[Lit] = set()
    pending = sorted(
        (l for l in cone.seeds if l in pos), key=lambda l: pos[l]
    )
    seen.update(pending)
    width = len(pending)
    while pending and pending[-1] != cone.decision:
        t = pending.pop()
        for p in pred.get(t, ()):
            if p not in seen:
                seen.add(p)
                # insert in trail order
                lo, hi = 0, len(pending)
                while lo < hi:
                    mid = (lo + hi) // 2
                    if pos[pending[mid]] < pos[p]:
                        lo = mid + 1
                    else:
                        hi = mid
                pending.insert(lo, p)
        width = max(width, len(pending))

    # depth = longest path
    depth_of: dict[Lit, int] = {}
    order = _toposort(cur, pred)
    for l in order:
        depth_of[l] = 1 + max((depth_of.get(p, 0) for p in pred[l]), default=0)
    depth = max(depth_of.values(), default=0)
    return width, depth, sharing


def _toposort(nodes: Iterable[Lit], pred: dict[Lit, set[Lit]]) -> list[Lit]:
    visited: set[Lit] = set()
    out: list[Lit] = []

    def dfs(n: Lit) -> None:
        if n in visited:
            return
        visited.add(n)
        for p in pred.get(n, ()):
            dfs(p)
        out.append(n)

    for n in nodes:
        dfs(n)
    return out


def _vars_chain(cls: list[Clause]) -> bool:
    """Do the cone clauses' variable sets overlap pairwise (form a
    connected hypergraph)? XOR/parity chains do; random ternary CNF
    almost never does."""
    if len(cls) < 2:
        return True
    vsets = [frozenset(abs(l) for l in c) for c in cls]
    # union-find connectivity
    parent = list(range(len(vsets)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(vsets)):
        for j in range(i + 1, len(vsets)):
            if vsets[i] & vsets[j]:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
    roots = {find(i) for i in range(len(vsets))}
    return len(roots) == 1


# ───────────────────────── prime implicates ─────────────────────────


def cone_prime_implicates(
    cone: ConflictCone, *, max_vars: int = 16
) -> list[Clause] | None:
    """The exact set of *valid, useful* learnable clauses from this cone.

    From first principles: a clause ``C`` is a valid learned clause iff
    (a) ``K ⊨ C`` where ``K`` is the cone CNF (soundness), and
    (b) ``C`` is falsified by the trail at conflict time (usefulness —
    a clause not falsified now isn't asserting after backjump).

    We compute the *prime* implicates among these — clauses not subsumed
    by any other valid learned clause. Each is a "best possible" learned
    clause; the 1-UIP is one of them; the count is the ground truth for
    "how much one conflict could have taught us."

    For tractability we enumerate over the cone variables only (the
    boundary plus current-level literals). Returns ``None`` when the
    cone has too many variables to enumerate.
    """
    # Substitute out level-0 (root) literals: they're permanently fixed,
    # so they vanish from learned clauses (and don't count as variables
    # for the truth-table enumeration).
    root_a = {abs(l): l > 0 for l in cone.roots}
    cls: list[frozenset[Lit]] = []
    for c in cone.cone_clauses:
        rc = []
        sat = False
        for l in c:
            v = abs(l)
            if v in root_a:
                if (root_a[v] and l > 0) or (not root_a[v] and l < 0):
                    sat = True  # clause satisfied by a root lit, drop
                    break
                continue  # root lit falsifies this literal; drop it
            rc.append(l)
        if not sat:
            cls.append(frozenset(rc))

    cone_vars = sorted({abs(l) for c in cls for l in c})
    if len(cone_vars) > max_vars:
        return None

    # The trail assignment at conflict time over the remaining cone vars.
    trail_a = {abs(l): l > 0 for l in cone.frontier | cone.current_level_lits}

    # Blocked minterms = the off-set of K. Implicates of K = clauses
    # falsified by exactly the blocked minterms.
    blocked: list[dict[int, bool]] = []
    for ba in itertools.product([False, True], repeat=len(cone_vars)):
        a = dict(zip(cone_vars, ba))
        if not all(_sat_clause(c, a) for c in cls):
            blocked.append(a)
    if not blocked:
        return []

    # Prime implicants of the off-set → prime implicates of K.
    primes = _prime_implicants(blocked, cone_vars)
    # Restrict to *useful* implicates: falsified by the trail.
    out: list[Clause] = []
    for cube in primes:
        cl = tuple(sorted(((-v if val else v) for v, val in cube), key=abs))
        if _falsified_by(cl, trail_a):
            out.append(cl)
    return filter_subsumed(out)


def _sat_clause(c: frozenset[Lit], a: dict[int, bool]) -> bool:
    for l in c:
        v = abs(l)
        if v not in a:
            return True
        if (a[v] and l > 0) or (not a[v] and l < 0):
            return True
    return False


def _falsified_by(c: Clause, a: dict[int, bool]) -> bool:
    for l in c:
        v = abs(l)
        if v not in a:
            return False  # unassigned literal: not falsified
        if (a[v] and l > 0) or (not a[v] and l < 0):
            return False
    return True


def _prime_implicants(
    minterms: list[dict[int, bool]], vars_: list[int]
) -> set[tuple[tuple[int, bool], ...]]:
    """Quine–McCluskey: merge minterms differing in one bit; the
    unmergeable cubes at the end are prime.

    Cubes are represented as bitmasks ``(mask, val)`` over the variable
    list — ``mask`` is the cared-about positions, ``val`` is their
    truth values. Merging two cubes with the same mask differing in one
    bit drops that bit from the mask. The grouped-by-popcount QM
    optimization keeps this from exploding.
    """
    n = len(vars_)
    pos = {v: i for i, v in enumerate(vars_)}
    full = (1 << n) - 1
    cubes: set[tuple[int, int]] = set()
    for m in minterms:
        v = 0
        for var, b in m.items():
            if b:
                v |= 1 << pos[var]
        cubes.add((full, v))

    primes: set[tuple[int, int]] = set()
    while cubes:
        # group by (mask, popcount(val & mask)) so we only compare
        # adjacent groups
        groups: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for c in cubes:
            mask, val = c
            groups.setdefault((mask, bin(val).count("1")), []).append(c)
        merged: set[tuple[int, int]] = set()
        used: set[tuple[int, int]] = set()
        for (mask, pc), grp in groups.items():
            nxt = groups.get((mask, pc + 1), [])
            for a in grp:
                for b in nxt:
                    diff = a[1] ^ b[1]
                    if diff & (diff - 1) == 0:  # power of 2
                        merged.add((mask & ~diff, a[1] & ~diff))
                        used.add(a)
                        used.add(b)
        primes |= cubes - used
        cubes = merged

    out: set[tuple[tuple[int, bool], ...]] = set()
    for mask, val in primes:
        cube = tuple(
            (vars_[i], bool(val >> i & 1)) for i in range(n) if mask >> i & 1
        )
        out.add(cube)
    return out


# ───────────────────────── learning strategies ─────────────────────────


@dataclass
class LearnLog:
    """Per-conflict record for the experiment."""

    cone_size: int  # |reasons| + 1
    cone_clauses: int  # number of reason clauses + conflict clause
    boundary_size: int
    n_uips: int
    n_cuts: int  # distinct cuts found (up to cap)
    n_nonsubsumed: int  # distinct mutually non-subsuming cuts
    n_implicates: int | None  # exact prime-implicate count, or None
    shape: str
    width: int  # cone DAG sources
    depth: int  # longest reason chain
    sharing: int  # cone DAG joins
    uip_clause_len: int


@dataclass
class Instrument:
    """A conflict hook that records per-conflict structure but learns
    nothing extra (so the search is unchanged)."""

    cap: int = 32
    do_implicates: bool = False
    max_implicate_vars: int = 14
    log: list[LearnLog] = field(default_factory=list)

    def __call__(self, cone: ConflictCone, uip_clause: Clause) -> Sequence[Clause]:
        uips = all_uip_cuts(cone)
        cuts = enumerate_cuts(cone, cap=self.cap)
        nonsub = filter_subsumed(cuts)
        shape = classify_cone(cone)
        impl = None
        if self.do_implicates:
            impl_list = cone_prime_implicates(
                cone, max_vars=self.max_implicate_vars
            )
            impl = len(impl_list) if impl_list is not None else None
        self.log.append(
            LearnLog(
                cone_size=len(cone.reasons) + 1,
                cone_clauses=len(cone.cone_clauses),
                boundary_size=len(cone.frontier) + 1,
                n_uips=len(uips),
                n_cuts=len(cuts),
                n_nonsubsumed=len(nonsub),
                n_implicates=impl,
                shape=shape.kind,
                width=shape.width,
                depth=shape.depth,
                sharing=shape.sharing,
                uip_clause_len=len(uip_clause),
            )
        )
        return [uip_clause]


@dataclass
class MultiLearn:
    """Learn the 1-UIP clause plus the next ``k-1`` non-subsumed cuts,
    ranked by length (shortest first).

    This is the simplest "more than one clause per conflict" scheme.
    It's a strict superset of 1-UIP in terms of derived consequences,
    but it pollutes the clause DB. The experiment measures whether the
    pollution outweighs the propagation gain.
    """

    k: int

    def __call__(self, cone: ConflictCone, uip_clause: Clause) -> Sequence[Clause]:
        if self.k <= 1:
            return [uip_clause]
        cuts = filter_subsumed(enumerate_cuts(cone, cap=4 * self.k))
        # always lead with the 1-UIP clause (it's the assertion clause)
        rest = [c for c in cuts if c != uip_clause]
        rest.sort(key=len)
        return [uip_clause, *rest[: self.k - 1]]


@dataclass
class ExtLearn:
    """Introduce extension variables to compress the conflict cone.

    *The general answer* to "what can we learn from a conflict richer
    than one clause." The cone is a circuit; we Tseitin its intermediate
    resolvents and learn one short clause over the new variables plus the
    definitions. Extended Resolution p-simulates cutting planes,
    polynomial calculus, and Frege — so anything learnable in those
    systems is learnable this way. The catch is choosing *which*
    extensions are worth introducing.

    This implementation uses the cone's *internal structure* as the
    signal:

    - For each cone-internal implied literal ``l`` whose reason clause is
      *binary* (``(l ∨ ¬a)``), no extension is needed — the reason chain
      is already propagation-friendly.
    - For each cone-internal ``l`` whose reason has ≥2 literals besides
      ``l``, define ``z_l ↔ ⋀_{m ∈ R(l), m≠l} ¬m`` (the "premise" gate)
      and learn the binary clause ``(¬z_l ∨ l)``. If the cone is reused,
      future propagation of the premises propagates ``z_l`` and then
      ``l``, short-circuiting the resolution chain.

    We rate-limit to avoid variable explosion: only introduce extensions
    when the cone is classified structured (XOR/eq/card), where the
    gates are likely to recur.

    Reuse is tracked by hashing the gate definition; if the same gate
    appears in a later cone, ``hit`` is incremented. The reuse rate is
    the predictor of whether ext-learn pays off.
    """

    next_var: int  # caller must seed this with n_vars + 1
    only_structured: bool = True
    gates: dict[frozenset[Lit], Lit] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0

    def __call__(self, cone: ConflictCone, uip_clause: Clause) -> Sequence[Clause]:
        shape = classify_cone(cone)
        if self.only_structured and shape.kind == "unstructured":
            return [uip_clause]

        out: list[Clause] = [uip_clause]
        # introduce a gate for each cone-internal node with a wide reason
        for lit, rc in cone.reasons.items():
            premises = frozenset(-m for m in rc if m != lit)
            if len(premises) < 2:
                continue
            if premises in self.gates:
                self.hits += 1
                z = self.gates[premises]
            else:
                self.misses += 1
                z = self.next_var
                self.next_var += 1
                self.gates[premises] = z
                # z ↔ ⋀ premises   (Tseitin AND)
                for p in premises:
                    out.append((-z, p))  # z → p
                out.append((z, *(-p for p in premises)))  # ⋀p → z
            out.append((-z, lit))  # z → l (the cone's would-be-forced edge)
        return out


# ───────────────────────── parity-constraint learning ─────────────────────────


@dataclass
class XorLearn:
    """When the cone is classified XOR, learn the parity constraint over
    the boundary instead of one clause from it.

    A parity constraint over ``k`` variables is exactly the set of
    ``2^(k-1)`` clauses of the right parity — exponentially many. Encoded
    with extension variables (a chain of binary XOR gates), it costs
    ``4(k-1)`` clauses. That's the "extension variables compress
    exponentially many implicates" win in its purest form.
    """

    next_var: int
    log: list[str] = field(default_factory=list)

    def __call__(self, cone: ConflictCone, uip_clause: Clause) -> Sequence[Clause]:
        shape = classify_cone(cone)
        if shape.kind != "xor":
            return [uip_clause]
        # Extract the boundary parity. The conflict means the boundary
        # assignment had the *wrong* parity. The constraint is over the
        # boundary literals.
        bvars = sorted({abs(l) for l in cone.frontier} | {abs(cone.decision)})
        if len(bvars) < 2 or len(bvars) > 10:
            return [uip_clause]
        # parity of the *blocked* assignment (the trail values)
        # cone.frontier contains the trail literals (true), so a positive
        # literal means the var is true.
        a = {abs(l): (l > 0) for l in cone.frontier}
        a[abs(cone.decision)] = cone.decision > 0
        bad_parity = sum(a[v] for v in bvars) % 2
        # constraint: ⊕_v v ≠ bad_parity, i.e. ⊕_v v = 1 - bad_parity
        out = [uip_clause]
        out.extend(_encode_xor_chain(bvars, 1 - bad_parity, self.next_var))
        self.next_var += max(0, len(bvars) - 2)
        self.log.append(f"learned parity over {bvars} = {1 - bad_parity}")
        return out


def _encode_xor_chain(vars_: list[int], parity: int, fresh: int) -> list[Clause]:
    """``⊕ vars_ = parity`` Tseitin'd as a chain of binary XOR gates."""
    if len(vars_) == 1:
        return [(vars_[0],) if parity else (-vars_[0],)]
    if len(vars_) == 2:
        a, b = vars_
        if parity == 1:
            return [(a, b), (-a, -b)]
        return [(a, -b), (-a, b)]
    out: list[Clause] = []
    prev = vars_[0]
    for v in vars_[1:-1]:
        z = fresh
        fresh += 1
        # z = prev ⊕ v
        out += [(-z, prev, v), (-z, -prev, -v), (z, -prev, v), (z, prev, -v)]
        prev = z
    # final: prev ⊕ vars_[-1] = parity
    out += _encode_xor_chain([prev, vars_[-1]], parity, fresh)
    return out
