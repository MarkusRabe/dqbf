"""SAT-certificate verifier: DQBF + AIGER Skolem bundle → DIMACS CNF.

Produces a propositional CNF whose **unsatisfiability** witnesses that
the Skolem functions satisfy the matrix for every universal assignment,
plus a JSON variable map for debugging. The CNF can be handed to any
off-the-shelf SAT solver; this module does not solve.

Also performs a structural **dependency check**: each existential's AIG
output may only depend on inputs in its declared dependency set.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from tools.verify.formats import Aag, Formula


def var(lit: int) -> int:
    return abs(lit)


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
    in_name_of = {aig.inputs[i]: aig.in_names.get(i) for i in range(len(aig.inputs))}
    for y in f.dependencies:
        out = aig.output_by_name(f"e{y}")
        if out is None:
            dep_violations.append(f"e{y}: no AIGER output")
            e_dimacs[y] = -TRUE
            continue
        cone = aig.cone_inputs(out)
        for c in cone:
            nm = in_name_of.get(c)
            if nm is None or not nm.startswith("u") or not nm[1:].isdigit():
                dep_violations.append(f"e{y}: cone reaches input {c} with no valid 'u<k>' name")
                continue
            uid = int(nm[1:])
            if uid not in f.dependencies[y]:
                if not f.is_universal(uid):
                    dep_violations.append(f"e{y}: input named u{uid} but {uid} is not a universal")
                else:
                    dep_violations.append(f"e{y}: depends on universal {uid} ∉ deps")
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


# --- optional SAT-solver backends -----------------------------------------


def solve_cnf(n_vars: int, clauses: list[list[int]]) -> tuple[bool | None, list[int] | None]:
    """SAT-solve via the first available backend.

    Returns (is_sat, model) where model is the list of true-polarity
    literals; (None, None) if no backend is installed.
    """
    try:
        from pysat.solvers import Solver  # type: ignore[import-not-found]

        with Solver(name="cadical195", bootstrap_with=clauses) as s:
            sat = s.solve()
            return (sat, s.get_model() if sat else None)
    except ImportError:
        pass
    for exe in ("cadical", "kissat"):
        path = shutil.which(exe)
        if not path:
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".cnf", delete=False) as tf:
            tf.write(f"p cnf {n_vars} {len(clauses)}\n")
            for c in clauses:
                tf.write(" ".join(str(x) for x in c) + " 0\n")
            tmp = tf.name
        cp = subprocess.run([path, tmp], capture_output=True, text=True)
        Path(tmp).unlink(missing_ok=True)
        if cp.returncode == 10:
            model = [
                int(t)
                for ln in cp.stdout.splitlines()
                if ln.startswith("v ")
                for t in ln[2:].split()
                if t != "0"
            ]
            return (True, model)
        if cp.returncode == 20:
            return (False, None)
        return (None, None)
    return (None, None)


def decode_model(model: list[int], varmap: dict[str, dict[str, int]]) -> dict[str, object]:
    """Turn a SAT model of the verification CNF into a counterexample."""
    pos = {abs(x) for x in model if x > 0}
    return {
        "universals": {u: (v in pos) for u, v in varmap["universals"].items()},
        "violated_clauses": [i for i, v in varmap["violated_clause"].items() if v in pos],
    }
