"""Property test: encode_verification is sound and complete on tiny instances.

For random (formula, AIG) pairs, the verification CNF must be UNSAT iff
the AIG is a semantically valid Skolem certificate (checked by
brute-force evaluation). Any mismatch is a verifier bug.
"""

from __future__ import annotations

import itertools
import random

import pytest

from tools.verify.formats import Aag, Formula
from tools.verify.sat import encode_verification


def _eval_aig(aig: Aag, inp: dict[int, bool]) -> dict[int, bool]:
    val: dict[int, bool] = {0: False}
    for lit in aig.inputs:
        val[lit] = inp[lit]
    for g, a, b in aig.gates:
        av = val[a & ~1] ^ bool(a & 1)
        bv = val[b & ~1] ^ bool(b & 1)
        val[g] = av and bv
    return val


def _ground_truth_valid(f: Formula, aig: Aag) -> bool:
    in_of_u = {}
    for i, lit in enumerate(aig.inputs):
        nm = aig.in_names.get(i, "")
        if nm.startswith("u") and nm[1:].isdigit():
            in_of_u[int(nm[1:])] = lit
    out_of_e = {}
    for y in f.dependencies:
        out = aig.output_by_name(f"e{y}")
        if out is None:
            return False
        out_of_e[y] = out
    for bits in itertools.product((False, True), repeat=len(f.universals)):
        ua = dict(zip(f.universals, bits, strict=True))
        ain = {lit: ua.get(u, False) for u, lit in in_of_u.items()}
        for lit in aig.inputs:
            ain.setdefault(lit, False)
        gv = _eval_aig(aig, ain)
        ev = {}
        for y, out in out_of_e.items():
            ev[y] = gv[out & ~1] ^ bool(out & 1)
        asg = {**ua, **ev}
        for cl in f.clauses:
            if not any(asg[abs(x)] == (x > 0) for x in cl):
                return False
    return True


def _brute_sat(n_vars: int, clauses: list[list[int]]) -> bool:
    for bits in range(1 << n_vars):
        a = {v + 1: bool(bits >> v & 1) for v in range(n_vars)}
        if all(any(a[abs(x)] == (x > 0) for x in c) for c in clauses):
            return True
    return False


def _rand_formula(rnd: random.Random) -> Formula:
    nu = rnd.randint(1, 2)
    ne = rnd.randint(1, 2)
    us = tuple(range(1, nu + 1))
    deps = {nu + 1 + i: frozenset(rnd.sample(us, k=rnd.randint(0, nu))) for i in range(ne)}
    nv = nu + ne
    lits = [v for v in range(1, nv + 1)] + [-v for v in range(1, nv + 1)]
    cls = tuple(
        frozenset(rnd.sample(lits, k=rnd.randint(1, min(3, len(lits)))))
        for _ in range(rnd.randint(1, 4))
    )
    return Formula(nv, us, deps, cls)


def _rand_aig(rnd: random.Random, f: Formula) -> Aag:
    nu = len(f.universals)
    inputs = [2 * (i + 1) for i in range(nu)]
    in_names = {i: f"u{u}" for i, u in enumerate(f.universals)}
    ng = rnd.randint(0, 2)
    gates = []
    avail = [0, 1] + inputs
    for k in range(ng):
        lhs = 2 * (nu + 1 + k)
        a = rnd.choice(avail) ^ rnd.randint(0, 1)
        b = rnd.choice(avail) ^ rnd.randint(0, 1)
        gates.append((lhs, a, b))
        avail.append(lhs)
    outs, out_names = [], {}
    for j, y in enumerate(sorted(f.dependencies)):
        # Only use inputs in deps(y) (so dep-violations don't dominate the fuzz space).
        ok = [0, 1] + [inputs[i] for i, u in enumerate(f.universals) if u in f.dependencies[y]]
        outs.append(rnd.choice(ok) ^ rnd.randint(0, 1))
        out_names[j] = f"e{y}"
    return Aag(inputs, outs, gates, in_names, out_names)


@pytest.mark.parametrize("seed", range(60))
def test_encoding_matches_ground_truth(seed: int) -> None:
    rnd = random.Random(seed)
    f = _rand_formula(rnd)
    aig = _rand_aig(rnd, f)
    enc = encode_verification(f, aig)
    if enc.dep_violations:
        return  # structural reject; out of scope for the semantic equivalence
    if enc.n_vars > 18:
        pytest.skip("too large")
    cnf_unsat = not _brute_sat(enc.n_vars, enc.clauses)
    truth = _ground_truth_valid(f, aig)
    assert cnf_unsat == truth, (
        f"seed={seed}: encoding says {'VALID' if cnf_unsat else 'INVALID'}, "
        f"ground truth is {'VALID' if truth else 'INVALID'}"
    )
