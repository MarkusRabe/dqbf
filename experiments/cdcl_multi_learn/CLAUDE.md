# experiments/cdcl_multi_learn/

A self-contained experimental directory: a small instrumented CDCL SAT
solver used as a *measuring instrument* to study what one CDCL conflict
actually teaches and what richer learned object — multiple clauses,
extension variables, parity constraints — the cone could yield.

This is **propositional SAT only**, no DQBF, no quantifiers. It shares
no code with `provers/` or `tools/`. It exists because the question
("how much does one conflict teach?") is the same question `frust`
asks at a higher level (`arbsolve` cells, Padoa interpolants), and
isolating it in propositional SAT was the fastest way to get clean data.

## Files

- `cdcl.py` — minimal CDCL with two-watched-literals, VSIDS, Luby
  restarts, 1-UIP. Pluggable conflict hook receives the full
  `ConflictCone` (the implication sub-DAG). ~500 lines.
- `conflict_analysis.py` — cut enumeration, prime-implicate
  computation, cone-DAG topology features, three learning hooks
  (`MultiLearn`, `ExtLearn`, `XorLearn`), offline XOR detection.
- `generators.py` — instance generators: Tseitin XOR chains/trees,
  equality chains/grids, ripple-carry adder/multiplier miters, PHP,
  sequential cardinality, random 3-SAT.
- `experiment.py` — Phase 3 (per-conflict cut/implicate counts) and
  Phase 6 (learning-strategy comparison) experiments. CSV output.
- `REPORT.md` — the writeup. Read this for the findings.

## Reproducing

```sh
python3 experiment.py            # everything
python3 experiment.py xor_chain  # one class
```

Phase 3 output → `phase3.csv` (cuts/implicates per conflict).
Phase 6 output → `phase6.csv` (1uip vs multi-k vs ext-r vs xor_off).

The Python CDCL handles ~30k conflicts in ~10 s. It is *not* a
production solver; it is an instrument.

## Headline findings

1. Every conflict admits 6–32 mutually-non-subsuming learnable clauses,
   on every problem class (XOR, equality, arithmetic, pigeonhole,
   random). The cone is information-rich. The variation is in what the
   cuts say, not how many there are.
2. Extension-by-factoring (Audemard et al.-style) is propagation-
   equivalent to the unfactored clause and never reduces conflicts in
   our experiments — even at 50–95% gate reuse. Bookkeeping, not power.
3. Parity-constraint learning (offline XOR detection + cone-derived
   parity) gives 1.5× on XOR/parity/adder cones, exactly 1.0× elsewhere.
   The win comes from logical strength, not encoding compactness.
4. The first heuristic parity learner (cone shape only) was 47%
   unsound on random 3-SAT. The cone of one conflict only proves one
   cut; learning anything stronger needs a deductive derivation from
   the input encoding's structure, not abductive inference from cone
   shape. Soundness has a wall.
5. Multi-learn (learn k cuts) helps on parity and cardinality (1.2–1.7×)
   and hurts on pigeonhole and multiplier (0.8×). Helps when the extra
   cuts say something genuinely different, hurts when they're
   near-redundant.
