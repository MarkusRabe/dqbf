"""Verify a Skolem certificate against a DQBF.

For each universal assignment, evaluate the Skolem functions and check
the matrix. Tiny-instance only (enumerates 2^|universals| assignments).
"""

from __future__ import annotations

from core.formula import Formula
from core.semantics import Skolem, _all_universal_assignments, _apply_skolem, eval_matrix


def verify_skolem(f: Formula, sk: Skolem) -> bool:
    if set(sk) != set(f.dependencies):
        return False
    for y, tbl in sk.items():
        for key in tbl:
            if len(key) != len(f.dependencies[y]):
                return False
    for ua in _all_universal_assignments(f):
        if not eval_matrix(f.clauses, _apply_skolem(f, sk, ua)):
            return False
    return True
