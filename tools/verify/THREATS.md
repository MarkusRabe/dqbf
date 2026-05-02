# Verifier threat model

Every case below is covered by at least one test in
`suite_sat_test.py` / `suite_unsat_test.py`. Cases marked ⚠ are ones
where the *initial* implementation was found to be incomplete.

## SAT certificate (`encode_verification` + dep check)

### Dependency-set violations
- S-D1  direct: `e_y` output literal is a universal input outside `deps(y)`
- S-D2  transitive: dependency reaches a forbidden universal through a gate chain
- S-D3  masked: forbidden universal AND-ed with constant 0 (cone still reaches it; output is const)
- S-D4  ⚠ unnamed input: AIGER input with no `i<k>` symbol — must still be treated as a forbidden dep
- S-D5  ⚠ input named something other than `u<int>` — must be rejected, not silently ignored
- S-D6  input named `u<k>` where `k` is not a declared universal — must be rejected
- S-D7  exact-match deps (output uses exactly `deps(y)`) — must be allowed
- S-D8  subset deps (output uses strict subset) — must be allowed
- S-D9  constant output (depends on nothing) — must be allowed
- S-D10 existential with empty dep set; output uses any input — must be rejected
- S-D11 inverted forbidden input (`¬u_k`) — must be rejected (cone should see through inversion)

### Missing / extra outputs
- S-O1  no AIGER output named `e_y` for some existential — recorded as dep-violation
- S-O2  extra AIGER output `e_k` for non-existential `k` — ignored
- S-O3  duplicate `o<i>` symbol entries — last-wins or error, but never accept-as-valid
- S-O4  output index in symbol table out of range

### AIGER parser edge cases
- S-A1  latches present (`L>0`) — reject
- S-A2  bad header token / wrong field count
- S-A3  gate lhs is odd (illegal in AIGER)
- S-A4  ⚠ gate lhs collides with an input literal
- S-A5  gate references undefined literal (lhs > 2·M)
- S-A6  output references undefined literal
- S-A7  empty file / no header
- S-A8  header counts disagree with body line count
- S-A9  symbol table before all gates parsed (malformed ordering)

### DQDIMACS parser edge cases
- S-P1  ⚠ clause literal whose variable is neither universal nor existential
- S-P2  variable declared both `a` and `d`
- S-P3  `d` line lists a non-universal as a dependency
- S-P4  missing `p cnf` header
- S-P5  empty file

### Encoding semantics
- S-E1  output literal is a constant 0 / constant 1 — substitution must use ±TRUE correctly
- S-E2  output literal is an inverted gate (odd) — substitution must propagate the sign
- S-E3  output literal IS an input literal directly (`e_y = u_x`) — should map to the universal's var
- S-E4  two existentials share the same AIGER output — allowed (same Skolem function)
- S-E5  formula with empty clause — every cert is INVALID (CNF must be SAT)
- S-E6  formula with tautological clause — that clause can never be the violated one
- S-E7  formula with no clauses — every cert is VALID (CNF must be UNSAT: `⋁∅`)
- S-E8  formula with no universals (propositional) — cert is a constant per existential
- S-E9  formula with no existentials — cert is empty AIG; matrix tautology check
- S-E10 large variable IDs / gaps in numbering

### Correct certs (must accept)
- S-V1..S-V8  hand-built valid certs for small formulas (identity, negation, AND, XOR, ITE, …)

## UNSAT certificate (`verify_proof`)

### Premise indexing
- U-I1  ⚠ premise index ≥ number of derived clauses so far — must reject, not crash
- U-I2  ⚠ premise index negative — must reject (Python list[-1] wraps!)
- U-I3  premise index points at the step itself

### Axiom
- U-X1  clause not in input — reject
- U-X2  clause in input, literals reordered — accept (frozenset)
- U-X3  tautological clause that IS in input — accept (it's still an axiom)
- U-X4  empty clause as axiom when input has empty clause — accept; ⊥ derived immediately

### Resolution
- U-R1  pivot variable not in either premise — reject
- U-R2  pivot in only one premise — reject
- U-R3  pivot present with same polarity in both — reject
- U-R4  resolvent is a tautology — reject (conservatively)
- U-R5  recorded clause ≠ the (∀-reduced) resolvent — reject
- U-R6  self-resolution (both premises same index, clause has `p` and `¬p`) — produces resolvent without `p,¬p`; must match
- U-R7  resolution producing the empty clause — accept

### ∀-reduction
- U-U1  recorded clause is the full reduction — accept
- U-U2  recorded clause is a partial reduction — **accept** (∀-red is per-literal; any subset of soundly-droppable universals is fine)
- U-U3  universal that IS in some existential's deps cannot be dropped — reject if recorded as dropped
- U-U4  universal with both polarities in clause cannot be dropped
- U-U5  clause with only universal literals reduces to ∅

### FEx / SFEx
- U-F1  `part` not ⊆ source clause — reject
- U-F2  recorded clause matches neither `left` nor `right` — reject
- U-F3  `fresh` collides with an existing universal — reject
- U-F4  ⚠ `fresh` reused by a SECOND, different fork (different `part`/`src`) — must reject
- U-F5  `fresh` reused by the sibling (same `part`, same `src`) — accept
- U-F6  empty `part` — accept (degenerate but sound)
- U-F7  `part` = whole clause — accept (degenerate)
- U-F8  sfex `c3` contains an existential literal — reject
- U-F9  sfex `c3` contains a literal whose var is not in the formula — reject
- U-F10 sfex `c3` empty — equivalent to fex; accept
- U-F11 fex on a clause that has no information fork — still sound; accept
- U-F12 ⚠ `fresh` < current n_vars but is neither existential nor universal (gap in IDs) — reject

### Proof shape
- U-S1  proof never derives ⊥ — reject
- U-S2  ⊥ derived, then later step is invalid — reject (conservative; documented)
- U-S3  empty proof — reject
- U-S4  unknown rule name — reject
- U-S5  step missing required field (e.g. `res` without `pivot`) — reject

### File / parse
- U-P1  `.frp` not valid JSON — error
- U-P2  `.frp` is JSON but not a list — error
- U-P3  `.frp` step missing `clause`/`rule` keys — error
- U-P4  DQDIMACS issues (S-P1..5) feed into `verify_proof` too

### Valid refutations (must accept)
- U-V1..U-V8  hand-built valid refutations exercising each rule
