#!/usr/bin/env bash
# Generate the adversarial corpus: tiny instances + valid certs + one
# mutation per risk. Run from `tools/verify_rs/tests/adversarial/`.
set -euo pipefail
cd "$(dirname "$0")"

# ─── tiny instances ─────────────────────────────────────────────────

# F1: ∀1 ∃2(1): (1∨2)∧(1∨¬2). UNSAT.
cat > f1.dqdimacs << 'EOF'
p cnf 2 2
a 1 0
d 2 1 0
1 2 0
1 -2 0
EOF

# F2: ∀1 ∃2(∅): (1∨2)∧(¬1∨¬2). UNSAT.
cat > f2.dqdimacs << 'EOF'
p cnf 2 2
a 1 0
d 2 0
1 2 0
-1 -2 0
EOF

# G1: ∀1 ∃2(1): (¬1∨2). SAT (y₂=1 is a model). For SAT-cert tests.
cat > g1.dqdimacs << 'EOF'
p cnf 2 1
a 1 0
d 2 1 0
-1 2 0
EOF

# G2: ∀1 ∀2 ∃3(1) ∃4(2): (3∨4). SAT (e.g. y₃=1).
cat > g2.dqdimacs << 'EOF'
p cnf 4 1
a 1 2 0
d 3 1 0
d 4 2 0
3 4 0
EOF

# ─── valid UNSAT certs ──────────────────────────────────────────────

cat > f1.valid.frp << 'EOF'
[{"clause":[1,2],"rule":"axiom"},{"clause":[1,-2],"rule":"axiom"},{"clause":[1],"rule":"res","premises":[0,1],"pivot":2},{"clause":[],"rule":"ured","premises":[2]}]
EOF

cat > f2.valid.frp << 'EOF'
[{"clause":[1,2],"rule":"axiom"},{"clause":[-1,-2],"rule":"axiom"},{"clause":[2],"rule":"ured","premises":[0]},{"clause":[-2],"rule":"ured","premises":[1]},{"clause":[],"rule":"res","premises":[2,3],"pivot":2}]
EOF

# ─── valid SAT certs ────────────────────────────────────────────────

# g1: y₂ = constant 1.  aag M=1 I=1 L=0 O=1 A=0; output literal = 1 (constant true).
cat > g1.valid.aag << 'EOF'
aag 1 1 0 1 0
2
1
i0 u1
o0 e2
EOF

# g2: y₃ = 1, y₄ = 0.  Two outputs, constant.
cat > g2.valid.aag << 'EOF'
aag 2 2 0 2 0
2
4
1
0
i0 u1
i1 u2
o0 e3
o1 e4
EOF

# ─── adversarial UNSAT mutations ───────────────────────────────────
# Each is a single-step mutation of a valid proof. The shell here just
# emits the file; the cross_check_test.sh harness asserts INVALID.

cat > f1.adv_premise_oob.frp << 'EOF'
[{"clause":[1,2],"rule":"axiom"},{"clause":[1,-2],"rule":"axiom"},{"clause":[1],"rule":"res","premises":[0,99],"pivot":2},{"clause":[],"rule":"ured","premises":[2]}]
EOF

cat > f1.adv_premise_forward.frp << 'EOF'
[{"clause":[1],"rule":"res","premises":[1,2],"pivot":2},{"clause":[1,2],"rule":"axiom"},{"clause":[1,-2],"rule":"axiom"},{"clause":[],"rule":"ured","premises":[0]}]
EOF

cat > f1.adv_no_refutation.frp << 'EOF'
[{"clause":[1,2],"rule":"axiom"},{"clause":[1,-2],"rule":"axiom"},{"clause":[1],"rule":"res","premises":[0,1],"pivot":2}]
EOF

cat > f1.adv_unknown_rule.frp << 'EOF'
[{"clause":[1,2],"rule":"axiom"},{"clause":[],"rule":"abracadabra","premises":[0]}]
EOF

cat > f1.adv_empty_proof.frp << 'EOF'
[]
EOF

cat > f1.adv_taut_clause.frp << 'EOF'
[{"clause":[1,2,-2],"rule":"axiom"}]
EOF

cat > f1.adv_huge_var.frp << 'EOF'
[{"clause":[9223372036854775807],"rule":"axiom"}]
EOF

cat > f1.adv_axiom_not_in_matrix.frp << 'EOF'
[{"clause":[2],"rule":"axiom"},{"clause":[],"rule":"ured","premises":[0]}]
EOF

cat > f1.adv_axiom_with_premise.frp << 'EOF'
[{"clause":[1,2],"rule":"axiom"},{"clause":[1,-2],"rule":"axiom","premises":[0]},{"clause":[1],"rule":"res","premises":[0,1],"pivot":2},{"clause":[],"rule":"ured","premises":[2]}]
EOF

cat > f1.adv_res_wrong_pivot.frp << 'EOF'
[{"clause":[1,2],"rule":"axiom"},{"clause":[1,-2],"rule":"axiom"},{"clause":[1],"rule":"res","premises":[0,1],"pivot":1},{"clause":[],"rule":"ured","premises":[2]}]
EOF

cat > f1.adv_res_no_pivot.frp << 'EOF'
[{"clause":[1,2],"rule":"axiom"},{"clause":[1,-2],"rule":"axiom"},{"clause":[1],"rule":"res","premises":[0,1]},{"clause":[],"rule":"ured","premises":[2]}]
EOF

cat > f1.adv_res_extra_lit.frp << 'EOF'
[{"clause":[1,2],"rule":"axiom"},{"clause":[1,-2],"rule":"axiom"},{"clause":[1,2],"rule":"res","premises":[0,1],"pivot":2},{"clause":[],"rule":"ured","premises":[2]}]
EOF

cat > f1.adv_res_missing_lit.frp << 'EOF'
[{"clause":[1,2],"rule":"axiom"},{"clause":[1,-2],"rule":"axiom"},{"clause":[],"rule":"res","premises":[0,1],"pivot":2}]
EOF

cat > f1.adv_res_same_polarity.frp << 'EOF'
[{"clause":[1,2],"rule":"axiom"},{"clause":[1,2],"rule":"axiom"},{"clause":[1],"rule":"res","premises":[0,1],"pivot":2},{"clause":[],"rule":"ured","premises":[2]}]
EOF

cat > f2.adv_res_taut_resolvent.frp << 'EOF'
[{"clause":[1,2],"rule":"axiom"},{"clause":[-1,-2],"rule":"axiom"},{"clause":[1,-1],"rule":"res","premises":[0,1],"pivot":2}]
EOF

cat > f1.adv_ured_drop_existential.frp << 'EOF'
[{"clause":[1,2],"rule":"axiom"},{"clause":[1],"rule":"ured","premises":[0]},{"clause":[1,-2],"rule":"axiom"},{"clause":[1],"rule":"res","premises":[0,2],"pivot":2},{"clause":[],"rule":"ured","premises":[3]}]
EOF

cat > f1.adv_ured_depended.frp << 'EOF'
[{"clause":[1,2],"rule":"axiom"},{"clause":[2],"rule":"ured","premises":[0]},{"clause":[1,-2],"rule":"axiom"},{"clause":[1],"rule":"res","premises":[0,2],"pivot":2},{"clause":[],"rule":"ured","premises":[3]}]
EOF

cat > f1.adv_ured_added_lit.frp << 'EOF'
[{"clause":[1,2],"rule":"axiom"},{"clause":[1,2,-1],"rule":"ured","premises":[0]}]
EOF

cat > f1.adv_ured_noop.frp << 'EOF'
[{"clause":[1,2],"rule":"axiom"},{"clause":[1,2],"rule":"ured","premises":[0]},{"clause":[1,-2],"rule":"axiom"},{"clause":[1],"rule":"res","premises":[0,2],"pivot":2},{"clause":[],"rule":"ured","premises":[3]}]
EOF

cat > f1.adv_bad_json.frp << 'EOF'
[{"clause":[1,2],"rule":"axio
EOF

# F3 for FEx adversarial cases.
cat > f3.dqdimacs << 'EOF'
p cnf 4 4
a 1 2 0
d 3 1 0
d 4 2 0
3 4 0
-3 -4 0
-1 2 3 0
1 -2 -3 0
EOF

cat > f3.adv_fex_part_not_subset.frp << 'EOF'
[{"clause":[3,4],"rule":"axiom"},{"clause":[3,5],"rule":"fex","premises":[0],"part":[3,1],"fresh":5}]
EOF

cat > f3.adv_fex_not_fresh.frp << 'EOF'
[{"clause":[3,4],"rule":"axiom"},{"clause":[3,2],"rule":"fex","premises":[0],"part":[3],"fresh":2}]
EOF

cat > f3.adv_fex_neither_half.frp << 'EOF'
[{"clause":[3,4],"rule":"axiom"},{"clause":[3,4,5],"rule":"fex","premises":[0],"part":[3],"fresh":5}]
EOF

cat > f3.adv_fex_wrong_polarity.frp << 'EOF'
[{"clause":[3,4],"rule":"axiom"},{"clause":[3,-5],"rule":"fex","premises":[0],"part":[3],"fresh":5}]
EOF

cat > f3.adv_fex_no_part.frp << 'EOF'
[{"clause":[3,4],"rule":"axiom"},{"clause":[3,5],"rule":"fex","premises":[0],"fresh":5}]
EOF

cat > f3.adv_sfex_c3_existential.frp << 'EOF'
[{"clause":[3,4],"rule":"axiom"},{"clause":[3,3,5],"rule":"sfex","premises":[0],"part":[3],"c3":[3],"fresh":5}]
EOF

cat > f3.adv_sfex_c3_missing.frp << 'EOF'
[{"clause":[3,4],"rule":"axiom"},{"clause":[3,5],"rule":"sfex","premises":[0],"part":[3],"c3":[-2],"fresh":5}]
EOF

cat > f3.adv_fex_with_c3.frp << 'EOF'
[{"clause":[3,4],"rule":"axiom"},{"clause":[-2,3,5],"rule":"fex","premises":[0],"part":[3],"c3":[-2],"fresh":5}]
EOF

# ─── adversarial SAT mutations ─────────────────────────────────────

# g1 SAT: y₂ = constant 1 satisfies (¬1∨2). y₂=0 fails at u₁=1.
cat > g1.adv_sat_wrong_const.aag << 'EOF'
aag 1 1 0 1 0
2
0
i0 u1
o0 e2
EOF

# g1: input symbol mislabelled as a non-universal.
cat > g1.adv_sat_wrong_input.aag << 'EOF'
aag 1 1 0 1 0
2
1
i0 u9
o0 e2
EOF

# g1: output symbol mislabelled (e9 is not an existential).
cat > g1.adv_sat_wrong_output.aag << 'EOF'
aag 1 1 0 1 0
2
1
i0 u1
o0 e9
EOF

# g1: missing output (no o0 symbol).
cat > g1.adv_sat_missing_output.aag << 'EOF'
aag 1 1 0 1 0
2
1
i0 u1
EOF

# g1: header lies (M=1 but A=1 declared).
cat > g1.adv_sat_bad_header.aag << 'EOF'
aag 1 1 0 1 1
2
1
4 2 2
i0 u1
o0 e2
EOF

# g2: dep leak — y₃ = u₂ (cone reads u₂ ∉ dep(y₃)={u₁}).
cat > g2.adv_sat_dep_leak.aag << 'EOF'
aag 2 2 0 2 0
2
4
4
0
i0 u1
i1 u2
o0 e3
o1 e4
EOF

# g2: a real .aag with a gate cycle (lhs uses itself indirectly).
# AIGER says lhs literals must be > rhs; a violating file should reject.
cat > g2.adv_sat_cycle.aag << 'EOF'
aag 4 2 0 2 2
2
4
6
0
6 8 2
8 6 4
i0 u1
i1 u2
o0 e3
o1 e4
EOF

# g2: output literal out of range.
cat > g2.adv_sat_oob.aag << 'EOF'
aag 2 2 0 2 0
2
4
99
0
i0 u1
i1 u2
o0 e3
o1 e4
EOF

echo "wrote $(ls *.dqdimacs *.frp *.aag | wc -l) corpus files"
