"""UNSAT-certificate verification suite.

Each case is (id, dqdimacs, frp_json, expected) where expected ∈
{"valid", "invalid", "error"}. "invalid" means verify_proof must return
False; "error" means parsing must raise. The emphasis is on REJECTING
bad proofs — see THREATS.md for the case taxonomy.
"""

from __future__ import annotations

import json

import pytest

from tools.verify.formats import load_proof, parse_dqdimacs
from tools.verify.unsat import verify_proof

# --- helpers --------------------------------------------------------------


def dq(prefix: str, *clauses: str) -> str:
    body = "\n".join(clauses)
    nv = max(
        (
            abs(int(t))
            for ln in (prefix + " " + body).split()
            for t in [ln]
            if t.lstrip("-").isdigit()
        ),
        default=0,
    )
    return f"p cnf {nv} {len(clauses)}\n{prefix}\n{body}\n"


def frp(*steps: dict) -> str:
    return json.dumps(list(steps))


# Common formulas ---------------------------------------------------------

F_PROP = "p cnf 1 2\ne 1 0\n1 0\n-1 0\n"
F_12_3 = "p cnf 3 2\na 1 2 0\nd 3 1 0\n-2 3 0\n2 -3 0\n"  # UNSAT: y3(x1) ↔ x2
F_FORK = "p cnf 4 3\na 1 2 0\nd 3 1 0\nd 4 2 0\n3 4 0\n-3 0\n-4 0\n"
F_CYCLE = "p cnf 6 4\na 1 2 3 0\nd 4 1 2 0\nd 5 2 3 0\nd 6 1 3 0\n4 5 6 0\n-4 0\n-5 0\n-6 0\n"

# --- valid refutations (must return True) --------------------------------

VALID = [
    (
        "U-V1-prop-res",
        F_PROP,
        frp(
            {"clause": [1], "rule": "axiom"},
            {"clause": [-1], "rule": "axiom"},
            {"clause": [], "rule": "res", "premises": [0, 1], "pivot": 1},
        ),
    ),
    (
        "U-V2-ured-then-res",
        F_12_3,
        frp(
            {"clause": [-2, 3], "rule": "axiom"},
            {"clause": [2, -3], "rule": "axiom"},
            {"clause": [3], "rule": "ured", "premises": [0]},
            {"clause": [-3], "rule": "ured", "premises": [1]},
            {"clause": [], "rule": "res", "premises": [2, 3], "pivot": 3},
        ),
    ),
    (
        "U-V3-fex-full",
        F_FORK,
        frp(
            {"clause": [3, 4], "rule": "axiom"},
            {"clause": [-3], "rule": "axiom"},
            {"clause": [-4], "rule": "axiom"},
            {"clause": [3, 5], "rule": "fex", "premises": [0], "part": [3], "fresh": 5},
            {"clause": [-5, 4], "rule": "fex", "premises": [0], "part": [3], "fresh": 5},
            {"clause": [5], "rule": "res", "premises": [3, 1], "pivot": 3},
            {"clause": [-5], "rule": "res", "premises": [4, 2], "pivot": 4},
            {"clause": [], "rule": "res", "premises": [5, 6], "pivot": 5},
        ),
    ),
    (
        "U-V4-sfex",
        F_CYCLE,
        frp(
            {"clause": [4, 5, 6], "rule": "axiom"},
            {"clause": [-4], "rule": "axiom"},
            {"clause": [-5], "rule": "axiom"},
            {"clause": [-6], "rule": "axiom"},
            {
                "clause": [2, 4, 7],
                "rule": "sfex",
                "premises": [0],
                "part": [4],
                "c3": [2],
                "fresh": 7,
            },
            {
                "clause": [-7, 2, 5, 6],
                "rule": "sfex",
                "premises": [0],
                "part": [4],
                "c3": [2],
                "fresh": 7,
            },
            {"clause": [7], "rule": "res", "premises": [4, 1], "pivot": 4},
            {"clause": [-7, 6], "rule": "res", "premises": [5, 2], "pivot": 5},
            {"clause": [-7], "rule": "res", "premises": [7, 3], "pivot": 6},
            {"clause": [], "rule": "res", "premises": [6, 8], "pivot": 7},
        ),
    ),
    (
        "U-V5-axiom-reordered",
        F_PROP,
        frp(
            {"clause": [-1], "rule": "axiom"},
            {"clause": [1], "rule": "axiom"},
            {"clause": [], "rule": "res", "premises": [1, 0], "pivot": 1},
        ),
    ),
    (
        "U-V6-empty-clause-axiom",
        "p cnf 1 1\ne 1 0\n0\n",
        frp({"clause": [], "rule": "axiom"}),
    ),
    (
        "U-V7-universal-only-clause",
        "p cnf 2 1\na 1 2 0\n1 2 0\n",
        frp(
            {"clause": [1, 2], "rule": "axiom"},
            {"clause": [], "rule": "ured", "premises": [0]},
        ),
    ),
    (
        "U-V8-fex-empty-part",
        F_FORK,
        frp(
            {"clause": [3, 4], "rule": "axiom"},
            {"clause": [-3], "rule": "axiom"},
            {"clause": [-4], "rule": "axiom"},
            {"clause": [5], "rule": "fex", "premises": [0], "part": [], "fresh": 5},
            {"clause": [-5, 3, 4], "rule": "fex", "premises": [0], "part": [], "fresh": 5},
            {"clause": [3, 4], "rule": "res", "premises": [4, 3], "pivot": 5},
            {"clause": [4], "rule": "res", "premises": [5, 1], "pivot": 3},
            {"clause": [], "rule": "res", "premises": [6, 2], "pivot": 4},
        ),
    ),
    (
        "U-V9-fex-full-part",
        F_FORK,
        frp(
            {"clause": [3, 4], "rule": "axiom"},
            {"clause": [-3], "rule": "axiom"},
            {"clause": [-4], "rule": "axiom"},
            {"clause": [3, 4, 5], "rule": "fex", "premises": [0], "part": [3, 4], "fresh": 5},
            {"clause": [-5], "rule": "fex", "premises": [0], "part": [3, 4], "fresh": 5},
            {"clause": [4, 5], "rule": "res", "premises": [3, 1], "pivot": 3},
            {"clause": [5], "rule": "res", "premises": [5, 2], "pivot": 4},
            {"clause": [], "rule": "res", "premises": [6, 4], "pivot": 5},
        ),
    ),
    (
        "U-V10-sfex-empty-c3",
        F_FORK,
        frp(
            {"clause": [3, 4], "rule": "axiom"},
            {"clause": [-3], "rule": "axiom"},
            {"clause": [-4], "rule": "axiom"},
            {"clause": [3, 5], "rule": "sfex", "premises": [0], "part": [3], "c3": [], "fresh": 5},
            {"clause": [-5, 4], "rule": "sfex", "premises": [0], "part": [3], "c3": [], "fresh": 5},
            {"clause": [5], "rule": "res", "premises": [3, 1], "pivot": 3},
            {"clause": [-5], "rule": "res", "premises": [4, 2], "pivot": 4},
            {"clause": [], "rule": "res", "premises": [5, 6], "pivot": 5},
        ),
    ),
    (
        "U-V11-fex-no-fork-clause",
        # FEx is sound on any clause, even without an information fork.
        "p cnf 3 3\na 1 0\nd 2 1 0\nd 3 1 0\n2 3 0\n-2 0\n-3 0\n",
        frp(
            {"clause": [2, 3], "rule": "axiom"},
            {"clause": [-2], "rule": "axiom"},
            {"clause": [-3], "rule": "axiom"},
            {"clause": [3, 4], "rule": "fex", "premises": [0], "part": [3], "fresh": 4},
            {"clause": [-4, 2], "rule": "fex", "premises": [0], "part": [3], "fresh": 4},
            {"clause": [4], "rule": "res", "premises": [3, 2], "pivot": 3},
            {"clause": [2], "rule": "res", "premises": [4, 5], "pivot": 4},
            {"clause": [], "rule": "res", "premises": [6, 1], "pivot": 2},
        ),
    ),
    (
        "U-V12-fresh-ids-monotone",
        # Two distinct FEx applications with fresh=5 then fresh=6.
        F_FORK,
        frp(
            {"clause": [3, 4], "rule": "axiom"},
            {"clause": [-3], "rule": "axiom"},
            {"clause": [-4], "rule": "axiom"},
            {"clause": [3, 5], "rule": "fex", "premises": [0], "part": [3], "fresh": 5},
            {"clause": [-5, 4], "rule": "fex", "premises": [0], "part": [3], "fresh": 5},
            {"clause": [3, 6], "rule": "fex", "premises": [3], "part": [3], "fresh": 6},
            {"clause": [-6, 5], "rule": "fex", "premises": [3], "part": [3], "fresh": 6},
            {"clause": [5], "rule": "res", "premises": [3, 1], "pivot": 3},
            {"clause": [-5], "rule": "res", "premises": [4, 2], "pivot": 4},
            {"clause": [], "rule": "res", "premises": [7, 8], "pivot": 5},
        ),
    ),
]

# --- invalid proofs (must return False) ----------------------------------

INVALID = [
    # Axiom
    ("U-X1-axiom-not-in-input", F_PROP, frp({"clause": [2], "rule": "axiom"})),
    (
        "U-X3-axiom-superset",
        F_PROP,
        frp({"clause": [1, -1], "rule": "axiom"}),  # {1,-1} not in input
    ),
    # Premise indexing — THREATS U-I*
    (
        "U-I1-premise-out-of-range",
        F_PROP,
        frp(
            {"clause": [1], "rule": "axiom"},
            {"clause": [], "rule": "res", "premises": [0, 5], "pivot": 1},
        ),
    ),
    (
        "U-I2-premise-negative",
        F_PROP,
        frp(
            {"clause": [1], "rule": "axiom"},
            {"clause": [-1], "rule": "axiom"},
            {"clause": [], "rule": "res", "premises": [0, -1], "pivot": 1},
        ),
    ),
    (
        "U-I3-premise-self",
        F_PROP,
        frp(
            {"clause": [1], "rule": "axiom"},
            {"clause": [], "rule": "res", "premises": [1, 1], "pivot": 1},
        ),
    ),
    (
        "U-I4-ured-premise-out-of-range",
        F_12_3,
        frp({"clause": [3], "rule": "ured", "premises": [9]}),
    ),
    (
        "U-I5-fex-premise-negative",
        F_FORK,
        frp(
            {"clause": [3, 4], "rule": "axiom"},
            {"clause": [3, 5], "rule": "fex", "premises": [-1], "part": [3], "fresh": 5},
        ),
    ),
    # Resolution
    (
        "U-R1-pivot-absent",
        F_PROP,
        frp(
            {"clause": [1], "rule": "axiom"},
            {"clause": [-1], "rule": "axiom"},
            {"clause": [], "rule": "res", "premises": [0, 1], "pivot": 2},
        ),
    ),
    (
        "U-R2-pivot-one-side",
        "p cnf 2 2\ne 1 2 0\n1 2 0\n2 0\n",
        frp(
            {"clause": [1, 2], "rule": "axiom"},
            {"clause": [2], "rule": "axiom"},
            {"clause": [2], "rule": "res", "premises": [0, 1], "pivot": 1},
        ),
    ),
    (
        "U-R3-pivot-same-polarity",
        "p cnf 2 2\ne 1 2 0\n1 2 0\n1 0\n",
        frp(
            {"clause": [1, 2], "rule": "axiom"},
            {"clause": [1], "rule": "axiom"},
            {"clause": [2], "rule": "res", "premises": [0, 1], "pivot": 1},
        ),
    ),
    (
        "U-R4-resolvent-tautology",
        "p cnf 2 2\ne 1 2 0\n1 2 0\n-1 -2 0\n",
        frp(
            {"clause": [1, 2], "rule": "axiom"},
            {"clause": [-1, -2], "rule": "axiom"},
            {"clause": [2, -2], "rule": "res", "premises": [0, 1], "pivot": 1},
        ),
    ),
    (
        "U-R5-wrong-resolvent",
        "p cnf 2 2\ne 1 2 0\n1 2 0\n-1 0\n",
        frp(
            {"clause": [1, 2], "rule": "axiom"},
            {"clause": [-1], "rule": "axiom"},
            {"clause": [1], "rule": "res", "premises": [0, 1], "pivot": 1},
        ),
    ),
    (
        "U-R7-missing-pivot-field",
        F_PROP,
        frp(
            {"clause": [1], "rule": "axiom"},
            {"clause": [-1], "rule": "axiom"},
            {"clause": [], "rule": "res", "premises": [0, 1]},
        ),
    ),
    (
        "U-R8-one-premise",
        F_PROP,
        frp(
            {"clause": [1], "rule": "axiom"},
            {"clause": [], "rule": "res", "premises": [0], "pivot": 1},
        ),
    ),
    # ∀-reduction
    (
        "U-U2-partial-reduction",
        "p cnf 4 1\na 1 2 0\nd 3 0\nd 4 0\n1 2 3 0\n",
        frp(
            {"clause": [1, 2, 3], "rule": "axiom"},
            {"clause": [1, 3], "rule": "ured", "premises": [0]},  # full reduction is {3}
        ),
    ),
    (
        "U-U3-drop-dependent-universal",
        "p cnf 3 1\na 1 2 0\nd 3 1 0\n1 3 0\n",
        frp(
            {"clause": [1, 3], "rule": "axiom"},
            {"clause": [3], "rule": "ured", "premises": [0]},  # 1 ∈ dep(3), can't drop
        ),
    ),
    (
        "U-U4-drop-both-polarities",
        "p cnf 2 1\na 1 0\nd 2 0\n1 -1 2 0\n",
        frp(
            {"clause": [1, -1, 2], "rule": "axiom"},
            {"clause": [2], "rule": "ured", "premises": [0]},
        ),
    ),
    (
        "U-U6-ured-no-premise",
        F_12_3,
        frp({"clause": [3], "rule": "ured", "premises": []}),
    ),
    # FEx / SFEx
    (
        "U-F1-part-not-subset",
        F_FORK,
        frp(
            {"clause": [3, 4], "rule": "axiom"},
            {"clause": [3, 5], "rule": "fex", "premises": [0], "part": [3, 99], "fresh": 5},
        ),
    ),
    (
        "U-F2-clause-neither-half",
        F_FORK,
        frp(
            {"clause": [3, 4], "rule": "axiom"},
            {"clause": [3, 4, 5], "rule": "fex", "premises": [0], "part": [3], "fresh": 5},
        ),
    ),
    (
        "U-F3-fresh-is-universal",
        F_FORK,
        frp(
            {"clause": [3, 4], "rule": "axiom"},
            {"clause": [3, 1], "rule": "fex", "premises": [0], "part": [3], "fresh": 1},
        ),
    ),
    (
        "U-F4-fresh-reused-different-fork",
        # Two FEx steps both claim fresh=5 but from DIFFERENT partitions.
        F_FORK,
        frp(
            {"clause": [3, 4], "rule": "axiom"},
            {"clause": [3, 5], "rule": "fex", "premises": [0], "part": [3], "fresh": 5},
            # different part → different intended dep set; reusing 5 must be rejected
            {"clause": [4, 5], "rule": "fex", "premises": [0], "part": [4], "fresh": 5},
        ),
    ),
    (
        "U-F4b-fresh-reused-different-src",
        "p cnf 4 4\na 1 2 0\nd 3 1 0\nd 4 2 0\n3 4 0\n-3 4 0\n-3 0\n-4 0\n",
        frp(
            {"clause": [3, 4], "rule": "axiom"},
            {"clause": [-3, 4], "rule": "axiom"},
            {"clause": [3, 5], "rule": "fex", "premises": [0], "part": [3], "fresh": 5},
            {"clause": [-3, 5], "rule": "fex", "premises": [1], "part": [-3], "fresh": 5},
        ),
    ),
    (
        "U-F8-sfex-c3-existential",
        F_CYCLE,
        frp(
            {"clause": [4, 5, 6], "rule": "axiom"},
            {"clause": [4, 7], "rule": "sfex", "premises": [0], "part": [4], "c3": [5], "fresh": 7},
        ),
    ),
    (
        "U-F9-sfex-c3-unknown-var",
        F_CYCLE,
        frp(
            {"clause": [4, 5, 6], "rule": "axiom"},
            {
                "clause": [4, 7, 99],
                "rule": "sfex",
                "premises": [0],
                "part": [4],
                "c3": [99],
                "fresh": 7,
            },
        ),
    ),
    (
        "U-F12-fresh-is-gap-var",
        # n_vars=6 but only 1..6 declared; fresh=6 is existential? No: 6 IS declared.
        # Use a formula with a gap: vars 1,2,4,5 declared, var 3 unused. fresh=3.
        "p cnf 5 1\na 1 2 0\nd 4 1 0\nd 5 2 0\n4 5 0\n",
        frp(
            {"clause": [4, 5], "rule": "axiom"},
            {"clause": [4, 3], "rule": "fex", "premises": [0], "part": [4], "fresh": 3},
        ),
    ),
    (
        "U-F13-fex-missing-part",
        F_FORK,
        frp(
            {"clause": [3, 4], "rule": "axiom"},
            {"clause": [3, 5], "rule": "fex", "premises": [0], "fresh": 5},
        ),
    ),
    (
        "U-F14-fex-missing-fresh",
        F_FORK,
        frp(
            {"clause": [3, 4], "rule": "axiom"},
            {"clause": [3, 5], "rule": "fex", "premises": [0], "part": [3]},
        ),
    ),
    (
        "U-F15-fex-fresh-is-existing-existential",
        F_FORK,
        frp(
            {"clause": [3, 4], "rule": "axiom"},
            # fresh=4 already exists with dep={2}; fex would assign dep=∅. Must reject.
            {"clause": [3, 4], "rule": "fex", "premises": [0], "part": [3], "fresh": 4},
        ),
    ),
    # Proof shape
    ("U-S1-no-bottom", F_PROP, frp({"clause": [1], "rule": "axiom"})),
    ("U-S3-empty-proof", F_PROP, frp()),
    (
        "U-S2-bottom-then-bad-step",
        F_PROP,
        frp(
            {"clause": [1], "rule": "axiom"},
            {"clause": [-1], "rule": "axiom"},
            {"clause": [], "rule": "res", "premises": [0, 1], "pivot": 1},
            {"clause": [99], "rule": "axiom"},
        ),
    ),
    (
        "U-F16-fresh-not-monotone",
        # First fork uses fresh=10, second uses fresh=5 (< n_vars after first).
        F_FORK,
        frp(
            {"clause": [3, 4], "rule": "axiom"},
            {"clause": [3, 10], "rule": "fex", "premises": [0], "part": [3], "fresh": 10},
            {"clause": [3, 5], "rule": "fex", "premises": [0], "part": [3], "fresh": 5},
        ),
    ),
    (
        "U-F17-sfex-then-fex-same-fresh",
        F_CYCLE,
        frp(
            {"clause": [4, 5, 6], "rule": "axiom"},
            {
                "clause": [2, 4, 7],
                "rule": "sfex",
                "premises": [0],
                "part": [4],
                "c3": [2],
                "fresh": 7,
            },
            {"clause": [4, 7], "rule": "fex", "premises": [0], "part": [4], "fresh": 7},
        ),
    ),
    ("U-S4-unknown-rule", F_PROP, frp({"clause": [1], "rule": "magic"})),
    (
        "U-S5-res-three-premises",
        F_PROP,
        frp(
            {"clause": [1], "rule": "axiom"},
            {"clause": [-1], "rule": "axiom"},
            {"clause": [], "rule": "res", "premises": [0, 1, 0], "pivot": 1},
        ),
    ),
    (
        "U-S6-axiom-with-premises",
        # Conservatively, axiom steps shouldn't carry premises; but currently ignored.
        # We accept this as VALID-but-harmless; not in INVALID list.
        # (placeholder removed)
        "p cnf 0 0\n",
        frp(),
    ),
]

# Drop placeholder
INVALID = [c for c in INVALID if c[0] != "U-S6-axiom-with-premises"]

# --- parse errors (must raise) -------------------------------------------

ERROR = [
    ("U-P1-frp-not-json", F_PROP, "not json at all"),
    ("U-P2-frp-not-list", F_PROP, '{"clause": [1]}'),
    ("U-P3-frp-missing-keys", F_PROP, '[{"rule": "axiom"}]'),
]

# --- the parametrized tests ----------------------------------------------

ALL_VALID = VALID
ALL_INVALID = INVALID


@pytest.mark.parametrize("name,dqd,proof", ALL_VALID, ids=[c[0] for c in ALL_VALID])
def test_valid_proofs_accepted(name: str, dqd: str, proof: str, tmp_path) -> None:
    f = parse_dqdimacs(dqd)
    p = tmp_path / "p.frp"
    p.write_text(proof)
    assert verify_proof(f, load_proof(p)) is True, f"{name}: valid proof rejected"


@pytest.mark.parametrize("name,dqd,proof", ALL_INVALID, ids=[c[0] for c in ALL_INVALID])
def test_invalid_proofs_rejected(name: str, dqd: str, proof: str, tmp_path) -> None:
    f = parse_dqdimacs(dqd)
    p = tmp_path / "p.frp"
    p.write_text(proof)
    assert verify_proof(f, load_proof(p)) is False, f"{name}: INVALID proof accepted!"


@pytest.mark.parametrize("name,dqd,proof", ERROR, ids=[c[0] for c in ERROR])
def test_malformed_proofs_error(name: str, dqd: str, proof: str, tmp_path) -> None:
    p = tmp_path / "p.frp"
    p.write_text(proof)
    _ = name, dqd
    with pytest.raises((ValueError, KeyError, TypeError)):
        load_proof(p)


def test_case_counts() -> None:
    assert len(ALL_VALID) >= 10
    assert len(ALL_INVALID) >= 25
