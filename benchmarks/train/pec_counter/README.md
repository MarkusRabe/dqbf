# pec_counter — Partial Equivalence Checking on a 3-bit counter

A single fixed circuit (`instances/counter.aag`) encoded as **PEC**
(Gitina et al., ICCD 2013 — see `docs/references/gitina_2013_pec_dqbf.md`)
at increasing BMC bound `k`.

## The circuit

A 3-bit synchronous up-counter with latches `l0,l1,l2` (LSB-first):

- `l0' = ¬l0`
- `l1' = l0 ⊕ l1`
- `l2' = (l0 ∧ l1) ⊕ l2`
- bad = `l0 ∧ l1 ∧ l2` (counter reaches 7)

**Gate 8** is `l0 ∧ l1` — the carry into bit 2. We mark it a **black
box**: its definition is erased and replaced by an unknown function of
its operand wires.

## What PEC asks

"Is there *any* implementation of the black-box gate(s) that makes bad
reachable in k steps?" Under the PEC encoding each black-box output bit
becomes a DQBF existential whose dependency set is **exactly the
universals feeding that gate's input wires** — here gate 8 depends only
on (the per-step copies of) `l0,l1`. This is genuine DQBF: the
restricted dependency set is what distinguishes it from QBF.

With `safe=False` the formula asserts reachability, so SAT ⇔ some
black-box implementation reaches bad@k. The intended AND makes bad
reachable at k=7, but other implementations of the unknown carry can
reach it sooner or never.

## Pipeline

```
COUNTER_AAG (in generate.py)        →  parse_seq_aag()
                                    →  tools/pec2dqbf/encode.py:
                                       encode_unrolled(seq, k, blackboxes={8}, safe=False)
                                    →  core.dqdimacs.dumps()  →  .dqdimacs.gz
```

`generate.py` sweeps `k ∈ {4,8,12,16,20,24,28,32}` and writes the `.aag`
source alongside the compiled instances.
