"""Minimal, instrumented CDCL solver.

This is a *measuring instrument*, not a solver: clarity and inspectability
over speed. Standard CDCL with two-watched-literal propagation, VSIDS,
Luby restarts, and 1-UIP learning — plus a pluggable conflict hook that
hands the analysis machinery the *whole* conflict cone (the implication
sub-DAG from the conflicting clause back to the current-level decision)
so we can study what *else* could have been learned besides the 1-UIP
clause.

The core observation this file exists to test: the 1-UIP clause is one
cut through the conflict graph. Every other reason-side/conflict-side
cut is also a valid learned clause. How many distinct ones are there?
Does any single richer object (a parity, a cardinality constraint, the
cone CNF itself) compactly subsume them?

Literals are signed DIMACS-style ints: var ``v`` is positive lit ``v``,
negative lit ``-v``. Clauses are tuples of ints. Variable 0 is unused.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

Lit = int
Clause = tuple[Lit, ...]


# ───────────────────────── conflict cone ─────────────────────────


@dataclass(frozen=True)
class ConflictCone:
    """The implication sub-DAG behind one conflict.

    Nodes are literals at the *current* decision level that the conflicting
    clause transitively depends on (via reason chains). Edges go from a
    literal to the literals in its reason clause that are also at the
    current level. The cone bottoms out at the decision literal (the unique
    current-level literal with no reason).

    ``frontier`` collects the literals at *lower* levels that the cone
    touches — those appear (negated) in *every* learned clause regardless
    of where we cut. The interesting choice is which subset of the
    current-level cone to leave on the reason side.
    """

    level: int
    decision: Lit  # the decision literal at `level`
    conflict_clause: Clause  # the clause that became all-false
    # current-level lit -> the clause that propagated it (decision has none)
    reasons: dict[Lit, Clause]
    # current-level lits that the conflicting clause directly mentions (negated)
    seeds: frozenset[Lit]
    # lower-level lits the cone touches; each appears negated in every cut
    frontier: frozenset[Lit]
    # level-0 (root-level) trail literals the cone touches. These are
    # permanently fixed; they're substituted out, never learned.
    roots: frozenset[Lit]
    # trail order of current-level literals (decision first)
    trail_order: tuple[Lit, ...]

    @property
    def current_level_lits(self) -> frozenset[Lit]:
        return frozenset(self.reasons) | {self.decision}

    @property
    def cone_clauses(self) -> list[Clause]:
        """The reason clauses + the conflicting clause: the CNF whose UNSAT
        (under the lower-level assignment) *is* the conflict."""
        return [*self.reasons.values(), self.conflict_clause]


# A conflict hook receives the cone and the standard 1-UIP learned clause.
# It returns the clause to actually learn (or several). Default: just the
# 1-UIP one. The instrument uses this to log alternatives without changing
# the search.
ConflictHook = Callable[[ConflictCone, Clause], Sequence[Clause]]


# ───────────────────────── solver ─────────────────────────


@dataclass
class Stats:
    decisions: int = 0
    conflicts: int = 0
    propagations: int = 0
    restarts: int = 0
    learned: int = 0
    learned_lits: int = 0


class Cdcl:
    """A small CDCL solver. Add clauses, then call :meth:`solve`."""

    def __init__(self, n_vars: int, conflict_hook: ConflictHook | None = None) -> None:
        self.n_vars = n_vars  # variables that participate in branching
        self._cap = n_vars  # capacity of the per-var arrays (grows on demand)
        self.clauses: list[Clause] = []
        self.is_learned: list[bool] = []
        # watches[lit] = list of clause indices that currently watch -lit
        # (i.e. the clause becomes unit/conflicting when lit is assigned).
        # We use the convention: a clause watches two of its literals; the
        # watch list is keyed by the *negation* of a watched literal so that
        # assigning that literal triggers a visit.
        self._watch: dict[Lit, list[int]] = {}
        # assignment: 0 unassigned, +1 true, -1 false (indexed by var)
        self._val: list[int] = [0] * (n_vars + 1)
        self._level: list[int] = [0] * (n_vars + 1)
        # reason: clause index that propagated this var, or None (decision/init)
        self._reason: list[int | None] = [None] * (n_vars + 1)
        # trail of assigned literals, in order
        self._trail: list[Lit] = []
        self._trail_lim: list[int] = []  # trail index at which each level started
        self._qhead = 0  # propagation queue head

        # VSIDS
        self._activity: list[float] = [0.0] * (n_vars + 1)
        self._var_inc = 1.0
        self._var_decay = 0.95

        # phase saving
        self._phase: list[int] = [-1] * (n_vars + 1)

        self.stats = Stats()
        self._hook = conflict_hook

    def _grow_to(self, n: int) -> None:
        """Grow the per-variable arrays to cover var ``n``. Used by
        extension-learning hooks that introduce fresh variables on the
        fly. New variables are *not* added to the branching pool —
        ``n_vars`` is unchanged — so they're only ever assigned by
        propagation, which is what extension definitions are for."""
        if n <= self._cap:
            return
        extra = n - self._cap
        self._val.extend([0] * extra)
        self._level.extend([0] * extra)
        self._reason.extend([None] * extra)
        self._activity.extend([0.0] * extra)
        self._phase.extend([-1] * extra)
        self._cap = n

    # ── clause management ──────────────────────────────────────────

    def add_clause(self, clause: Iterable[Lit]) -> bool:
        """Add an input clause. Returns False if the formula is now trivially
        UNSAT (empty clause, or a unit that conflicts at level 0)."""
        c = tuple(sorted(set(clause), key=abs))
        if any(-l in c for l in c):
            return True  # tautology, drop
        if not c:
            return False
        if len(c) == 1:
            return self._enqueue(c[0], None)
        self._add_to_db(c, learned=False)
        return True

    def _add_to_db(self, c: Clause, *, learned: bool) -> int:
        idx = len(self.clauses)
        self.clauses.append(c)
        self.is_learned.append(learned)
        # watch the first two lits
        self._watch.setdefault(-c[0], []).append(idx)
        self._watch.setdefault(-c[1], []).append(idx)
        return idx

    # ── trail ───────────────────────────────────────────────────────

    def _value(self, lit: Lit) -> int:
        v = self._val[abs(lit)]
        return v if lit > 0 else -v

    def _enqueue(self, lit: Lit, reason: int | None) -> bool:
        v = abs(lit)
        cur = self._value(lit)
        if cur > 0:
            return True
        if cur < 0:
            return False
        self._val[v] = 1 if lit > 0 else -1
        self._level[v] = self._cur_level()
        self._reason[v] = reason
        self._trail.append(lit)
        return True

    def _cur_level(self) -> int:
        return len(self._trail_lim)

    def _new_level(self) -> None:
        self._trail_lim.append(len(self._trail))

    def _backtrack(self, level: int) -> None:
        if self._cur_level() <= level:
            return
        lim = self._trail_lim[level]
        for lit in self._trail[lim:]:
            v = abs(lit)
            self._phase[v] = self._val[v]
            self._val[v] = 0
            self._reason[v] = None
        del self._trail[lim:]
        del self._trail_lim[level:]
        self._qhead = min(self._qhead, len(self._trail))

    # ── propagation ─────────────────────────────────────────────────

    def _propagate(self) -> int | None:
        """Returns the index of a conflicting clause, or None."""
        while self._qhead < len(self._trail):
            lit = self._trail[self._qhead]
            self._qhead += 1
            self.stats.propagations += 1
            watchlist = self._watch.get(lit)
            if not watchlist:
                continue
            i = 0
            while i < len(watchlist):
                ci = watchlist[i]
                c = self.clauses[ci]
                # which lit is being falsified?
                if -c[0] == lit:
                    a, b = c[0], c[1]
                else:
                    a, b = c[1], c[0]
                # a is the falsified watch; b is the other watch
                if self._value(b) > 0:
                    i += 1
                    continue
                # try to find a new watch among c[2:]
                found = False
                for j in range(2, len(c)):
                    if self._value(c[j]) >= 0:  # not false
                        # swap c[j] into watch position
                        new_c = list(c)
                        # ensure a is at index 0 or 1; we'll rebuild
                        ai = 0 if new_c[0] == a else 1
                        new_c[ai], new_c[j] = new_c[j], new_c[ai]
                        new_clause = tuple(new_c)
                        self.clauses[ci] = new_clause
                        # remove from current watchlist, add to new one
                        watchlist[i] = watchlist[-1]
                        watchlist.pop()
                        self._watch.setdefault(-new_clause[ai], []).append(ci)
                        found = True
                        break
                if found:
                    continue
                # no new watch: clause is unit on b, or conflicting
                if self._value(b) < 0:
                    return ci  # conflict
                if not self._enqueue(b, ci):
                    return ci
                i += 1
        return None

    # ── VSIDS ──────────────────────────────────────────────────────

    def _bump(self, v: int) -> None:
        self._activity[v] += self._var_inc
        if self._activity[v] > 1e100:
            for i in range(1, self.n_vars + 1):
                self._activity[i] *= 1e-100
            self._var_inc *= 1e-100

    def _decay(self) -> None:
        self._var_inc /= self._var_decay

    def _pick_branch(self) -> Lit | None:
        best, best_a = 0, -1.0
        for v in range(1, self.n_vars + 1):
            if self._val[v] == 0 and self._activity[v] > best_a:
                best, best_a = v, self._activity[v]
        if best == 0:
            return None
        return best * (self._phase[best] if self._phase[best] != 0 else -1)

    # ── conflict analysis (1-UIP) + cone extraction ───────────────

    def _extract_cone(self, conflict_idx: int) -> ConflictCone:
        """Walk reason chains from the conflicting clause back to the
        current-level decision, collecting every reason clause touched."""
        level = self._cur_level()
        conf_c = self.clauses[conflict_idx]
        reasons: dict[Lit, Clause] = {}
        frontier: set[Lit] = set()
        roots: set[Lit] = set()
        seeds: set[Lit] = set()
        decision: Lit | None = None
        seen: set[int] = set()  # vars at current level we've already expanded

        def add_lower(t: Lit) -> None:
            if self._level[abs(t)] == 0:
                roots.add(t)
            else:
                frontier.add(t)

        # BFS over the reason DAG restricted to the current level.
        queue: list[Lit] = []
        for l in conf_c:
            v = abs(l)
            if self._level[v] == level:
                # the literal as it sits on the trail (true), not as it
                # appears (false) in the conflict clause
                t = -l
                seeds.add(t)
                if v not in seen:
                    seen.add(v)
                    queue.append(t)
            else:
                add_lower(-l)
        while queue:
            t = queue.pop()
            v = abs(t)
            ri = self._reason[v]
            if ri is None:
                decision = t
                continue
            rc = self.clauses[ri]
            reasons[t] = rc
            for m in rc:
                if m == t:
                    continue
                mv = abs(m)
                tm = -m  # the trail literal
                if self._level[mv] == level:
                    if mv not in seen:
                        seen.add(mv)
                        queue.append(tm)
                else:
                    add_lower(tm)

        assert decision is not None, "conflict cone must reach a decision"
        # trail order at the current level (decision first)
        lim = self._trail_lim[level - 1]
        cur_lits = frozenset(reasons) | {decision}
        order = tuple(l for l in self._trail[lim:] if l in cur_lits)
        return ConflictCone(
            level=level,
            decision=decision,
            conflict_clause=conf_c,
            reasons=reasons,
            seeds=frozenset(seeds),
            frontier=frozenset(frontier),
            roots=frozenset(roots),
            trail_order=order,
        )

    def _analyze_1uip(self, cone: ConflictCone) -> tuple[Clause, int]:
        """Standard 1-UIP. Returns (learned clause, backjump level)."""
        # Resolve the conflicting clause against reasons of current-level
        # implied literals in reverse trail order until exactly one
        # current-level literal remains.
        learned: set[Lit] = set()
        seen: set[int] = set()
        path_count = 0
        for l in cone.conflict_clause:
            v = abs(l)
            self._bump(v)
            if v in seen:
                continue
            seen.add(v)
            if self._level[v] == cone.level:
                path_count += 1
            elif self._level[v] > 0:
                learned.add(l)

        # walk the trail backwards
        i = len(self._trail) - 1
        uip: Lit | None = None
        while True:
            while abs(self._trail[i]) not in seen or self._level[abs(self._trail[i])] != cone.level:
                i -= 1
            t = self._trail[i]
            i -= 1
            path_count -= 1
            if path_count == 0:
                uip = t
                break
            ri = self._reason[abs(t)]
            assert ri is not None
            for m in self.clauses[ri]:
                if m == t:
                    continue
                v = abs(m)
                self._bump(v)
                if v in seen:
                    continue
                seen.add(v)
                if self._level[v] == cone.level:
                    path_count += 1
                elif self._level[v] > 0:
                    learned.add(m)

        learned.add(-uip)
        clause = tuple(sorted(learned, key=abs))
        # backjump level = second-highest level in the clause
        levels = sorted({self._level[abs(l)] for l in clause if l != -uip}, reverse=True)
        bj = levels[0] if levels else 0
        return clause, bj

    # ── main loop ───────────────────────────────────────────────────

    def solve(self, *, max_conflicts: int | None = None) -> bool | None:
        """Returns True (SAT), False (UNSAT), or None (budget exhausted)."""
        # initial propagation at level 0
        if self._propagate() is not None:
            return False

        luby_idx = 0
        restart_budget = self._luby(luby_idx) * 32
        conflicts_since_restart = 0

        while True:
            confl = self._propagate()
            if confl is not None:
                self.stats.conflicts += 1
                conflicts_since_restart += 1
                if max_conflicts is not None and self.stats.conflicts >= max_conflicts:
                    return None
                if self._cur_level() == 0:
                    return False
                cone = self._extract_cone(confl)
                learned, bj = self._analyze_1uip(cone)
                if self._hook is not None:
                    extra = list(self._hook(cone, learned))
                else:
                    extra = [learned]
                self._backtrack(bj)
                # grow var arrays for any extension vars the hook introduced
                hi = max((abs(l) for c in extra for l in c), default=0)
                if hi > self._cap:
                    self._grow_to(hi)
                # Add all learned clauses, then propagate any that are
                # already unit under the post-backtrack assignment.
                # This handles both the assertion clause (the 1-UIP
                # clause is unit on the UIP after backjump) and any
                # extension-definition clauses the hook introduced (a
                # `z ↔ (a ∧ b)` definition is unit on `z` if `a` and
                # `b` are already assigned at lower levels). Without
                # this, an extension-shortened assertion clause stays
                # blocked because `z` never propagates.
                added: list[int] = []
                for lc in extra:
                    if len(lc) == 1:
                        self._enqueue(lc[0], None)
                        continue
                    ci = self._add_to_db(lc, learned=True)
                    added.append(ci)
                    self.stats.learned += 1
                    self.stats.learned_lits += len(lc)
                # iterate to a fixpoint over the just-added clauses;
                # the main propagation loop will pick up any further
                # consequences once these are enqueued
                changed = True
                while changed:
                    changed = False
                    for ci in added:
                        c = self.clauses[ci]
                        if any(self._value(l) > 0 for l in c):
                            continue
                        un = [l for l in c if self._value(l) == 0]
                        if len(un) == 1:
                            self._enqueue(un[0], ci)
                            changed = True
                self._decay()
                if conflicts_since_restart >= restart_budget:
                    self._backtrack(0)
                    luby_idx += 1
                    restart_budget = self._luby(luby_idx) * 32
                    conflicts_since_restart = 0
                    self.stats.restarts += 1
            else:
                lit = self._pick_branch()
                if lit is None:
                    return True
                self._new_level()
                self.stats.decisions += 1
                self._enqueue(lit, None)

    @staticmethod
    def _luby(x: int) -> int:
        # Luby sequence (0-indexed): 1,1,2,1,1,2,4,1,1,2,1,1,2,4,8,...
        size, seq = 1, 0
        while size < x + 1:
            seq += 1
            size = 2 * size + 1
        while size - 1 != x:
            size = (size - 1) >> 1
            seq -= 1
            x %= size
        return 1 << seq

    # ── accessor for the conflict hook ─────────────────────────────

    def level_of(self, lit: Lit) -> int:
        return self._level[abs(lit)]

    def assignment(self) -> dict[int, int]:
        return {v: self._val[v] for v in range(1, self.n_vars + 1) if self._val[v]}


def solve_cnf(
    n_vars: int,
    clauses: Iterable[Iterable[Lit]],
    *,
    conflict_hook: ConflictHook | None = None,
    max_conflicts: int | None = None,
) -> tuple[bool | None, Stats]:
    s = Cdcl(n_vars, conflict_hook=conflict_hook)
    for c in clauses:
        if not s.add_clause(c):
            return False, s.stats
    return s.solve(max_conflicts=max_conflicts), s.stats
