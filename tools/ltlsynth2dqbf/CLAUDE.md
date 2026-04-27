# tools/ltlsynth2dqbf/ — LTL Bounded Synthesis → DQBF

Encode bounded reactive synthesis (find an `n`-state Mealy machine
realizing an LTL spec) as a DQBF.

## Encoding

For state bound `n`, universally quantify a **source state**, a **target
state**, and the **environment input**; existentially quantify the
system's **transition function** `δ(s, i)` and **output function**
`λ(s, i)` with dependency sets `{s, i}` — *not* including the target
state `t`. The matrix asserts that the annotated run on the universal
co-Büchi automaton of `¬φ` stays bounded. DQBF lets `s` and `t` both be
universal while `δ`/`λ` ignore `t`, giving an encoding **linear** in `n`
where the QBF version is quadratic.

## References

- Faymonville, Finkbeiner, Tentrup. *Encodings of Bounded Synthesis.*
  TACAS 2017.
  https://link.springer.com/chapter/10.1007/978-3-662-54577-5_20
- Faymonville, Finkbeiner, Rabe, Tentrup. *BoSy: An Experimentation
  Framework for Bounded Synthesis.* CAV 2017.
  https://arxiv.org/abs/1803.09566
- Input format: TLSF (SYNTCOMP). https://arxiv.org/abs/1604.02284
- Reference implementation: BoSy (Swift).
  https://github.com/reactive-systems/bosy

## Plan

- [ ] TLSF parser (or shell out to `syfco` to normalize to LTL).
- [ ] LTL → universal co-Büchi automaton (via `spot` bindings).
- [ ] DQBF encoder per TACAS'17 §4; emit DQDIMACS + symbol map so a SAT
      certificate reads back as `δ`/`λ` AIGER → a Mealy machine.
- [ ] Golden tests on a handful of SYNTCOMP toy specs; diff against
      BoSy's DQBF output where obtainable.
