"""Tests for collatz generator.

`core.semantics.is_true` is infeasible (Tseitin aux blow up the Skolem
space), so ground truth is established by (a) unit-propagating the CNF
step against a Python reference, and (b) cross-checking the smallest
direct-CNF instances against dqbdd/hqs/pedant — which now agree, since
the encodings no longer go through EQFOB's `fun` bitblast.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from benchmarks.train.collatz.generate import (
    STEPS,
    _Cnf,
    _collatz_step,
    collatz_transition,
    encode_succinct,
    encode_tonly,
    eqfob_unrolled,
    known_expected,
)
from core import dqdimacs
from tools.eqfob.eqfob.bitblast import bitblast
from tools.eqfob.eqfob.parse import parse
from tools.eqfob.eqfob.typecheck import check
from tools.hwmc2dqbf_indinv.encode import encode_indinv

ROOT = Path(__file__).resolve().parents[4]
SOLVERS = {
    "dqbdd": ROOT / "third_party/dqbdd/Release/src/dqbdd",
    "hqs": ROOT / "third_party/hqs/HQS/build/src/hqs/hqs2",
    "pedant": ROOT / "third_party/pedant/build/src/pedant",
}


def _solve(f, solver: str) -> str | None:
    bin_ = SOLVERS[solver]
    if not bin_.is_file():
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".dqdimacs", delete=False) as tf:
        tf.write(dqdimacs.dumps(f))
        p = tf.name
    cp = subprocess.run([str(bin_), p], capture_output=True, text=True, timeout=30)
    Path(p).unlink(missing_ok=True)
    for ln in (cp.stdout + cp.stderr).splitlines():
        s = ln.strip()
        if s in ("UNSAT", "[RESULT] UNSAT", "UNSATISFIABLE", "s UNSATISFIABLE"):
            return "unsat"
        if s in ("SAT", "[RESULT] SAT", "SATISFIABLE", "s SATISFIABLE"):
            return "sat"
    return None


# ---- step-function CNF correctness ---------------------------------------


def _ref_step(v: int, n: int, shortcut: bool) -> int:
    mask = (1 << n) - 1
    if v <= 1:
        return 1
    if v & 1 == 0:
        return v >> 1
    r = (3 * v + 1) & mask
    return r >> 1 if shortcut else r


@pytest.mark.parametrize("step", STEPS)
def test_step_cnf_matches_reference(step: str) -> None:
    n = 6
    c = _Cnf()
    s = [c.fe(frozenset()) for _ in range(n)]
    nx = _collatz_step(c, s, step, frozenset())
    for v in range(1 << n):
        val = {abs(c.TRUE): True}
        for i in range(n):
            val[s[i]] = bool((v >> i) & 1)
        changed = True
        while changed:
            changed = False
            for cl in c.clauses:
                un, sat = [], False
                for L in cl:
                    a = val.get(abs(L))
                    if a is None:
                        un.append(L)
                    elif a == (L > 0):
                        sat = True
                        break
                if sat or len(un) != 1:
                    continue
                val[abs(un[0])] = un[0] > 0
                changed = True
        got = sum(1 << i for i in range(n) if val.get(abs(nx[i]), False) == (nx[i] > 0))
        assert got == _ref_step(v, n, step == "shortcut"), f"{step} v={v}"


@pytest.mark.parametrize("step", STEPS)
def test_transition_matches_reference(step: str) -> None:
    n = 6
    tr = collatz_transition(n, step)
    for v in range(1 << n):
        val: dict[int, bool] = {tr.state[i]: bool((v >> i) & 1) for i in range(n)}
        changed = True
        cls = tr.defs + tr.trans
        while changed:
            changed = False
            for c in cls:
                un, sat = [], False
                for L in c:
                    a = val.get(abs(L))
                    if a is None:
                        un.append(L)
                    elif a == (L > 0):
                        sat = True
                        break
                if sat or len(un) != 1:
                    continue
                val[abs(un[0])] = un[0] > 0
                changed = True
        got = sum(1 << i for i in range(n) if val.get(tr.next_state[i], False))
        assert got == _ref_step(v, n, step == "shortcut")


# ---- structural -----------------------------------------------------------


def test_tonly_prefix_shape() -> None:
    f = encode_tonly(n=16, k=6, step="shift")
    assert len(f.universals) == 12  # 2K
    sizes = {len(d) for d in f.dependencies.values()}
    assert 6 in sizes  # f bits at dep={t} or {t'}


def test_succinct_is_genuine_dqbf() -> None:
    f = encode_succinct(n=8, k=4, step="shift")
    assert len(f.universals) == 16  # N + 2K
    deps = {frozenset(d) for d in f.dependencies.values() if d}
    twelve = [d for d in deps if len(d) == 12]
    assert len(twelve) >= 2 and twelve[0] != twelve[1]


@pytest.mark.parametrize("step", STEPS)
def test_unrolled_compiles(step: str) -> None:
    f = bitblast(check(parse(eqfob_unrolled(n=8, k=4, step=step))))
    assert f.n_vars > 0 and len(f.clauses) > 0


def test_indinv_encodes() -> None:
    f = encode_indinv(collatz_transition(8, "shift"), source="test")
    assert len(f.universals) == 16
    eight = [d for d in f.dependencies.values() if len(d) == 8]
    assert len(eight) >= 2


# ---- ground truth via solver cross-check ---------------------------------


def _tonly_gt(n: int, k: int, shortcut: bool) -> bool:
    for start in range(1 << n):
        v, ok = start, True
        for _ in range(1 << k):
            if v <= 1:
                ok = False
                break
            v = _ref_step(v, n, shortcut)
        if ok:
            return True
    return False


@pytest.mark.skipif(not SOLVERS["dqbdd"].is_file(), reason="dqbdd not built")
@pytest.mark.parametrize("step", ["shift", "shortcut"])
@pytest.mark.parametrize("n,k", [(4, 2), (4, 3), (6, 3), (6, 4)])
def test_tonly_ground_truth(step: str, n: int, k: int) -> None:
    want = "sat" if _tonly_gt(n, k, step == "shortcut") else "unsat"
    f = encode_tonly(n=n, k=k, step=step)
    for sv in ("dqbdd", "hqs", "pedant"):
        if not SOLVERS[sv].is_file():
            continue
        got = _solve(f, sv)
        assert got == want, f"{sv} n={n} k={k} step={step}: got={got} ref={want}"


@pytest.mark.skipif(not SOLVERS["dqbdd"].is_file(), reason="dqbdd not built")
def test_indinv_tiny() -> None:
    """N=4, M=2: starts {0..3}. 3→10 sets bit 3 → bad reachable → UNSAT."""
    f = encode_indinv(collatz_transition(4, "shift"), source="test")
    assert _solve(f, "dqbdd") == "unsat"


# ---- expected-result derivation ------------------------------------------


def test_known_expected_monotone() -> None:
    assert known_expected("unrolled", "shift", n=16, k=8) == "unsat"
    assert known_expected("tonly", "shift", n=16, k=6) == "sat"
    assert known_expected("tonly", "shift", n=16, k=10) == "unknown"
    assert known_expected("succinct", "shift", n=16, k=6) == "unknown"


# ---- captured EQFOB-fun anomaly (out of scope, tracked) ------------------


@pytest.mark.skipif(not SOLVERS["dqbdd"].is_file(), reason="dqbdd not built")
def test_eqfob_fun_disagreement() -> None:
    """EQFOB's `fun` bitblast yields a formula on which dqbdd/hqs say
    UNSAT but pedant (and a hand-crafted equivalent — see direct-CNF
    `encode_tonly`) say SAT. v1's `succinct` instances go through this
    path. Tracked here so it doesn't silently regress; not a v2 bug."""
    src = (
        "param N = 4\nparam K = 2\nfun f : bv[K] -> bv[N]\n"
        "forall t : bv[K]\nforall tp : bv[K]\n"
        "((tp == t + 1) && (tp != 0)) -> (f(tp) == f(t) + 1)\n"
        "f(t) != 1\nf(t) != 0\n"
    )
    f = bitblast(check(parse(src)))
    d = _solve(f, "dqbdd")
    p = _solve(f, "pedant")
    if d is not None and p is not None:
        assert d != p, "EQFOB-fun anomaly resolved — re-evaluate v1 succinct"
