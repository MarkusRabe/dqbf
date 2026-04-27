"""SAT-certificate verifier: DQBF + AIGER Skolem bundle → DIMACS CNF.

Produces a propositional CNF whose **unsatisfiability** witnesses that
the Skolem functions satisfy the matrix for every universal assignment,
plus a JSON variable map for debugging. The CNF can be handed to any
off-the-shelf SAT solver; this module does not solve.

Also performs a structural **dependency check**: each existential's AIG
output may only depend on inputs in its declared dependency set.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from pathlib import Path

from core.aiger import Aag
from core.formula import Formula, var
from core.semantics import Skolem, _all_universal_assignments, _apply_skolem, eval_matrix


@dataclass
class VerifyCNF:
    n_vars: int
    clauses: list[list[int]]
    varmap: dict[str, dict[str, int]] = field(default_factory=dict)
    dep_violations: list[str] = field(default_factory=list)

    def write_dimacs(self, path: str | Path) -> None:
        with open(path, "w") as f:
            f.write("c dqbf-verify: UNSAT here => certificate VALID\n")
            f.write(f"p cnf {self.n_vars} {len(self.clauses)}\n")
            for c in self.clauses:
                f.write(" ".join(str(x) for x in c) + " 0\n")

    def write_map(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.varmap, indent=2, sort_keys=True))


def encode_verification(f: Formula, aig: Aag) -> VerifyCNF:
    """Build the CNF asserting ∃ū. ¬matrix(ū, skolem(ū))."""
    clauses: list[list[int]] = []
    next_id = 1

    def fresh() -> int:
        nonlocal next_id
        v = next_id
        next_id += 1
        return v

    # 1. universal vars: keep stable IDs (one fresh per universal)
    u_dimacs: dict[int, int] = {u: fresh() for u in f.universals}

    # 2. AIGER input lit -> dimacs var, via name "u<id>"
    aig_in_u: dict[int, int] = {}
    for i, lit in enumerate(aig.inputs):
        name = aig.in_names.get(i, "")
        if name.startswith("u"):
            uid = int(name[1:])
            if uid in u_dimacs:
                aig_in_u[lit] = u_dimacs[uid]

    # 3. AIGER gate vars
    gate_dimacs: dict[int, int] = {}

    def aig_to_dimacs(aiglit: int) -> int:
        if aiglit <= 1:
            return 0  # constant; handled by caller
        v = aiglit & ~1
        neg = aiglit & 1
        if v in aig_in_u:
            d = aig_in_u[v]
        elif v in gate_dimacs:
            d = gate_dimacs[v]
        else:
            d = fresh()
            gate_dimacs[v] = d
        return -d if neg else d

    TRUE = fresh()
    clauses.append([TRUE])

    def lit_or_const(aiglit: int) -> int:
        if aiglit == 0:
            return -TRUE
        if aiglit == 1:
            return TRUE
        return aig_to_dimacs(aiglit)

    for g, a, b in aig.gates:
        gd = aig_to_dimacs(g)
        ad = lit_or_const(a)
        bd = lit_or_const(b)
        clauses += [[-gd, ad], [-gd, bd], [gd, -ad, -bd]]

    # 4. existential -> AIGER output lit -> dimacs lit; dependency check
    e_dimacs: dict[int, int] = {}
    dep_violations: list[str] = []
    in_name_of = {aig.inputs[i]: n for i, n in aig.in_names.items()}
    for y in f.dependencies:
        out = aig.output_by_name(f"e{y}")
        if out is None:
            dep_violations.append(f"e{y}: no AIGER output")
            e_dimacs[y] = -TRUE
            continue
        cone = aig.cone_inputs(out)
        used = {int(in_name_of[c][1:]) for c in cone if in_name_of.get(c, "").startswith("u")}
        extra = used - set(f.dependencies[y])
        if extra:
            dep_violations.append(f"e{y}: depends on universals {sorted(extra)} ∉ deps")
        e_dimacs[y] = lit_or_const(out)

    # 5. matrix substitution: each DQBF literal -> dimacs literal
    def subst_lit(lit: int) -> int:
        v = var(lit)
        base = u_dimacs[v] if f.is_universal(v) else e_dimacs[v]
        return base if lit > 0 else -base

    # 6. ¬matrix: introduce one "violated_i" per clause, v_i → ¬ℓ for each ℓ, assert ⋁ v_i
    violated: list[int] = []
    for clause in f.clauses:
        vi = fresh()
        violated.append(vi)
        for lit in clause:
            clauses.append([-vi, -subst_lit(lit)])
    clauses.append(list(violated))

    varmap = {
        "universals": {str(k): v for k, v in u_dimacs.items()},
        "existentials": {str(k): v for k, v in e_dimacs.items()},
        "aiger_gates": {str(k): v for k, v in gate_dimacs.items()},
        "violated_clause": {str(i): v for i, v in enumerate(violated)},
        "TRUE": {"const": TRUE},
    }
    return VerifyCNF(
        n_vars=next_id - 1, clauses=clauses, varmap=varmap, dep_violations=dep_violations
    )


# --- tiny-instance fallback (kept for tests; enumerates 2^|U|) ------------


def verify_skolem(f: Formula, sk: Skolem) -> bool:
    if set(sk) != set(f.dependencies):
        return False
    for y, tbl in sk.items():
        n = len(f.dependencies[y])
        if set(tbl) != set(itertools.product((False, True), repeat=n)):
            return False
    for ua in _all_universal_assignments(f):
        if not eval_matrix(f.clauses, _apply_skolem(f, sk, ua)):
            return False
    return True
