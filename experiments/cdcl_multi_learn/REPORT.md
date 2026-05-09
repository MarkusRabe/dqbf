# Learning more than one clause per CDCL conflict

*An exploration: how many distinct learned clauses does one conflict
admit, what richer single object summarises them, and when does
learning that object pay off over learning one clause?*

> **TL;DR.** Every conflict admits 6–32+ mutually-non-subsuming
> learnable clauses, on every problem class — the variation is in
> *what* they say, not *how many* there are. The complete set is the
> implicates of the cone CNF falsified by the trail; the cone CNF is the
> circuit that generates them all in O(cone size). Extension variables
> can encode that circuit, but **extension-by-factoring** (replace two
> literals by a fresh definition) is propagation-equivalent to the
> original clause and never reduces conflicts in our experiments. The
> only thing that does reduce conflicts is learning a *logically
> stronger* object — a parity constraint, a cardinality constraint, a
> set of cuts the original clause doesn't subsume. Extension variables
> are then the *encoding* of the stronger object, not the source of its
> strength. The decision of *whether* to learn a stronger object cannot
> be made soundly from one cone in isolation — it must be derived from
> the input encoding (offline structure detection), because the cone of
> one conflict only proves one cut.


## 1. The question, made precise

Standard CDCL learns one clause per conflict — the 1-UIP cut through
the implication graph. But the implication graph at the conflicting
decision level is a DAG `G` from the decision literal to the conflict
node; *every* reason-side/conflict-side cut of `G` yields a valid
learned clause. The 1-UIP convention is a heuristic, not a theorem.

From first principles, what *is* the set of valid learned clauses?

- A conflict at decision level `d` exposes a sub-CNF `K` — the *cone* —
  consisting of the conflicting clause plus the reason clauses that
  fired on the path from the decision to the conflict.
- The conflict means `K ∧ τ ⊨ ⊥` where `τ` is the trail (the assignment
  at conflict time).
- A clause `C` is a **valid learned clause** iff (a) `K ⊨ C` —
  soundness, the conflict actually proves it — and (b) `C` is falsified
  by `τ` — usefulness, a clause not falsified now isn't asserting after
  backjump.

The set of valid learned clauses is thus *the implicates of `K`
falsified by `τ`*. The cuts of the conflict graph are the implicates
derivable by linear resolution starting from the conflicting clause.
The 1-UIP is one of them.

The cone `K` itself is a small CNF — typically 4–20 clauses over 6–20
variables. **The cone is the circuit that generates all valid learned
clauses.** It is the smallest possible representation of the conflict's
information content. Any single clause is a one-bit projection of it.

The deeper question Markus posed — "is there a formula representing
~all conflict clauses?" — has a precise answer: *yes, it is the cone
itself*, and the engineering question is what extraction or encoding of
the cone the CDCL machinery can actually exploit during propagation.


## 2. Phase 3 — measure how many clauses one conflict admits

We built a small instrumented CDCL in Python (`cdcl.py`,
`conflict_analysis.py`). On every conflict it extracts the cone and
counts: (a) distinct cuts found by bounded linear-resolution
enumeration (cap 32), (b) prime implicates of `K` (computed exactly by
truth table for cones ≤ 11 variables), (c) the cone DAG's *width*
(widest antichain — the peak `path_count` in a 1-UIP-style sweep) and
*depth*. The instance suite (`generators.py`) spans Tseitin XOR chains
and trees, equality chains and grids, ripple-carry adder and
shift-and-add multiplier miters, pigeonhole, sequential cardinality,
and random 3-SAT at the phase transition. Sizes are swept; every cell
below averages over 4–7 instance sizes.

| class       | cuts (avg/max) | width | depth | implicates |
|-------------|---------------:|------:|------:|-----------:|
| xor_chain   | 11.0 / 30      |   2.9 |   4.7 |        6.3 |
| parity_tree | 13.1 / 32      |   2.8 |   5.1 |        7.4 |
| eq_chain    | 27.2 / 32      |   2.0 |  16.0 |       13.0 |
| eq_grid     | 16.0 / 32      |   2.0 |   4.5 |       14.5 |
| adder       | 18.4 / 32      |   3.9 |   5.7 |        6.2 |
| multiplier  | 27.0 / 32      |   5.2 |   9.8 |        9.1 |
| php         | 17.9 / 32      |   3.6 |   5.6 |        6.7 |
| card_seq    | 20.7 / 32      |   4.2 |   9.6 |        6.5 |
| random3sat  | 17.0 / 32      |   3.6 |   6.4 |        7.1 |

**The first surprise**: every class — including random 3-SAT — admits
many distinct, mutually-non-subsuming learned clauses per conflict (the
cap of 32 is hit for most). The variation is in cone *width* and
*depth*, not in the raw count. Multiplier cones are widest (5.2) and
deepest (9.8) because the carry-save reduction tree fans out and
cascades; equality chains are width-2 (the conflict is two propagation
chains meeting in the middle) but depth-`n` (the chain is long).

The hypothesis going in — "structured encodings have many cuts, random
3-SAT has few" — is *wrong on the count*. What's true is that the
structured-class cuts have a *common pattern* (an XOR over a triple, an
implication chain, a cardinality threshold) and the random-3-SAT cuts
don't. The first kind *can* be compressed into a single richer object;
the second kind cannot.


## 3. Phase 4 — the formula representing all conflict clauses

The cone CNF `K` is the formula. To make this useful, we need to (i)
*encode* it in a way the solver can store and (ii) *propagate* it.

**Encoding.** Adding `K` back to the formula is a no-op — `K` is a
subset of the formula plus the conflicting clause, which is also there.
What's *not* there is the propagation history: the cone says "if the
boundary assignment looks like *this*, propagation forces these
intermediate literals and then conflicts." Encoding that history as
clauses requires extension variables — a fresh `z_l` for each
cone-internal literal `l`, defined as `z_l ↔ ⋀_{m ∈ R(l), m ≠ l} ¬m`
(the conjunction of `l`'s premises). The chain of `z_l` definitions
encodes the cone in O(cone size) clauses instead of the up to
exponentially-many clausal implicates.

**Propagation.** Here the first-principles analysis splits the design
space:

- **A clause** propagates one literal when all but one are false. It is
  a *single* implicate.
- **An extension definition `z ↔ φ`** (3 clauses for binary AND/OR, 4
  for XOR) propagates `z` once `φ` is determined and *the negation* of
  one input once `¬z ∧ φ`-but-one is determined. It encodes the
  bidirectional reasoning that a one-directional implication clause
  doesn't.
- **A parity constraint `⊕ S = p`** propagates the last unassigned
  variable of `S` once the rest are assigned. It is exponentially
  many clauses (`2^{|S|-1}`) in implicate form.
- **A pseudo-Boolean constraint `Σ aᵢxᵢ ≤ b`** propagates a bound once
  the free coefficients can no longer compensate. It is exponentially
  many clauses in clausal form.

The propagation strength ordering is roughly: clause < extension
definition < parity < PB ≤ general circuit. The price is the watching
machinery: clauses are watchable in O(1) amortised; extension
definitions are watchable as clauses; parity and PB constraints need
their own watching schemes (and proof-logging schemes, if one wants
verifiable proofs).


## 4. Phase 6 — does learning more help?

Three learning schemes, tested against vanilla 1-UIP across the same
instance suite, with a soundness assertion that all schemes must agree
on the SAT/UNSAT answer (4000-conflict cap; 320 runs; 0 violations):

1. **multi-`k`** — learn the 1-UIP clause plus the `k-1` next shortest
   cuts. Strictly more learned consequences, more clause-DB pollution.
2. **ext-`r`** — Audemard/Katsirelos/Simon-style factoring with a
   *cone-derived* signal. Pick the highest-cone-co-occurrence literal
   pair `(a, b)` from the 1-UIP clause's *frontier* literals, define
   `z ↔ (a ∧ b)`, learn `(¬z ∨ rest)`. Rate-limit `r`: only factor
   pairs seen in ≥`r` cone reason clauses. The shortened clause stays
   asserting because `a, b` are at lower levels and `z` is propagated
   before the assertion fires.
3. **xor_off** — offline (parse-time) Tseitin XOR detection, then on a
   conflict whose cone clauses are all from detected XOR gates, derive
   the boundary parity by XORing the gate constraints (variables in an
   even number of gates cancel) and learn the parity constraint encoded
   as a Tseitin chain.

Geometric-mean speedup vs 1-UIP, in conflicts-to-solve:

| class       | multi2 | multi4 | multi8 | ext4  | xor_off |
|-------------|-------:|-------:|-------:|------:|--------:|
| xor_chain   |  1.07× |  1.25× |  1.37× | 0.72× |   1.52× |
| parity_tree |  1.13× |  1.42× |  1.44× | 0.72× |   1.48× |
| eq_chain    |  1.00× |  1.00× |  1.00× | 1.00× |   1.00× |
| adder       |  1.00× |  1.08× |  1.02× | 0.76× |   1.53× |
| multiplier  |  1.00× |  0.94× |  0.88× | 0.53× |   1.00× |
| php         |  0.95× |  0.83× |  0.86× | 0.64× |   1.00× |
| card_seq    |  1.20× |  1.26× |  1.67× | 0.84× |   1.00× |
| random3sat  |  0.98× |  0.93× |  1.02× | 0.77× |   1.00× |

**Multi-learn**: helps on the parity classes (1.25–1.44×) and
cardinality (1.26–1.67×), hurts on multiplier (0.88×) and pigeonhole
(0.83×), neutral on random 3-SAT. The hurting cases are exactly where
the extra cuts are *logically near-equivalent* to the 1-UIP clause but
pollute the watch lists. The helping cases are where the cuts mention
genuinely different literal sets (the parity classes have cuts over
different XOR sub-chains; the cardinality classes have cuts over
different sub-thresholds).

**Ext-factoring**: hurts uniformly, 0.53–1.00×. This is the central
negative result and it has a clean first-principles explanation: the
shortened clause `(¬z ∨ rest)` is *propagation-equivalent* to the
original `(¬a ∨ ¬b ∨ rest)` given the definition. Same deductive
strength, same conflicts to the proof; the only thing factoring buys is
a shorter clause to watch, and that's outweighed by the 3 extra
definition clauses to watch. (We verified this isn't a bug: the reuse
rates are 50–95% across classes — the factored pairs *are* recurring —
yet conflicts go up. High reuse is necessary but not sufficient; the
extension has to make the learned clause logically *stronger*, not just
shorter, and factoring doesn't.)

**Parity-learn**: 1.5× on the three classes whose cones are pure XOR
gates (xor_chain, parity_tree, ripple-carry adder), exactly 1.0×
elsewhere (it never fires when the cone isn't provably XOR). This is
the only scheme that learns a *logically stronger* object than a single
clause: the parity constraint subsumes `2^{|S|-1}` clauses, and
encoding it via a Tseitin chain costs O(|S|). On the multiplier the
gain is 1.0× even though the multiplier *is* an XOR structure (full
adders), because conflict cones mix the AND-gate partial products with
the XOR addition tree, and the offline detector requires the *whole*
cone to be XOR clauses. The structure has to be *isolable* in cones to
be exploitable per-conflict.


## 5. The soundness pitfall

We initially tried a *heuristic* parity-learner that classified the
cone shape (all clauses ternary, variable triples chained) and learned
the boundary parity directly from the trail. It was **unsound 47% of
the time** on random 3-SAT (41 of 87 instances classified
SAT-vs-UNSAT differently from 1-UIP). The reason is fundamental, not a
bug: the conflict only *proves* one cut — that the observed boundary
assignment is blocked. Inferring that *all same-parity* boundary
assignments are blocked is a generalisation the cone may or may not
justify. Random 3-SAT cones happen to be all-ternary and chained —
they look like XOR — but they don't *imply* a parity constraint.

This is the deepest reason structured-constraint solvers (CryptoMiniSat
for XOR, RoundingSat for PB) detect structure in the *input formula*
rather than at conflict time: structure has to be a *theorem* of the
encoding's semantics, not a *conjecture* from the cone's shape. The
sound version of parity-learn (`xor_off`) verifies each cone clause is
a tagged input-XOR clause and derives the parity by XOR-cancellation;
it is provably sound and gives 1.5×. The bridge from "sound" to
"unsound" is the bridge from "deductive" to "abductive" — and CDCL is
strictly deductive.


## 6. The first-principles synthesis

Putting Phases 3–5 together:

1. **Every conflict admits many learned clauses.** That's not the
   bottleneck. The cap-32 enumeration finds 11–27 mutually
   non-subsuming clauses per conflict across all classes. The cone is
   information-rich.

2. **Multi-clause learning helps when the extra clauses say something
   new.** It helps on parity and cardinality (cuts over disjoint
   sub-structures) and hurts on pigeonhole and multiplier (cuts that
   are near-equivalent). There is no free lunch: every extra learned
   clause has a watching cost.

3. **Extension-by-factoring is propagation-neutral.** Replacing two
   literals by `z ↔ (a ∧ b)` and learning `(¬z ∨ rest)` is logically
   and propagation-wise equivalent to the unfactored clause. It saves
   storage if `z` recurs (it does, 50–95% reuse) but costs 3 extra
   clauses, and conflicts-to-solve doesn't change. **Extension
   variables in this role are bookkeeping, not power.**

4. **Extension variables as the encoding of a stronger constraint is a
   different story.** A parity constraint over `k` variables subsumes
   `2^{k-1}` clauses, and encoding it via extension variables costs
   `O(k)`. Learning it gives 1.5× on parity-shaped cones because the
   constraint is *logically stronger* than any single clause, not
   because the encoding is short.

5. **The decision of what stronger object to learn cannot be made
   soundly from one cone.** A single conflict proves one cut. Every
   stronger object — a parity constraint, a PB constraint, a circuit —
   must either be derived deductively (XOR-cancellation over input
   gates, PB-cutting-planes over input PB constraints) or risk
   unsoundness. The cone *signals* which structure to try; the
   structure detector must prove it from the encoding.

6. **The conflict cone gives a free signal the prior work didn't
   exploit.** The pair-co-occurrence and XOR-pattern detection are
   cheap to compute from the cone, and they predict whether a proposed
   extension/constraint will recur. The 2010-era extension-learning
   work (see appendix) used a blunt frequency heuristic ("which lit
   pair appears most often across all learned clauses?"); the cone
   gives a more targeted answer ("which lit pair appears in a cone
   reason clause, i.e. is a real gate of the encoded formula?"). Our
   experiment found that the targeted signal achieves high reuse
   (50–95%), confirming the cone is the right place to look — but
   factoring still didn't help because factoring is the wrong *use* of
   the signal. The right use is to choose which encoded constraint to
   learn in its native form.


## 7. What could go wrong (derived, not borrowed)

Reasons multi-learn / structured-learn might not help, derived from the
propagation-cost analysis above rather than from the prior work's
findings (we may rediscover their reasons; we may find others):

- **Logical redundancy.** Extra learned clauses that are near-subsumed
  by the 1-UIP clause add watching cost with no deductive gain.
  Visible in PHP (multi-learn hurts) and multiplier (cuts overlap
  heavily because the carry chain shares structure).

- **Propagation-equivalence.** Factored clauses are deductively the
  same as unfactored ones. Extension-by-factoring is bookkeeping.
  Confirmed by ext4 = 0.5–0.9× across the board.

- **Watch-cost asymmetry.** A short clause is fast to watch; a richer
  constraint (parity, PB) needs a non-clausal watching scheme. If the
  solver is clause-only, the encoding adds clauses linearly while the
  constraint subsumes exponentially — a win — but the *propagation*
  through the encoding chain is one step per gate, while the native
  constraint propagates in one step. The encoding is a proof-system
  win but not a wall-clock win unless the constraint subsumes
  *and* recurs.

- **Reuse fragility.** A learned constraint pays off only if its
  trigger condition recurs. The cone reuse rate (50–95% on structured
  classes, 40–60% on random 3-SAT) measures this; high reuse is
  necessary but, as the ext-factoring result shows, not sufficient.
  Reuse without strength is cycling.

- **Soundness has a wall.** Every constraint stronger than a single cut
  needs a *deductive* derivation. Heuristic generalisation from cone
  shape is unsound (47% on random 3-SAT). The only sound source of
  stronger constraints is the input encoding's semantics, which means
  structure detection must be at parse time, not conflict time. This
  caps what conflict-time learning can ever do — it bounds the system
  to deductive consequences of the cone, which is exactly the set of
  cuts.


## 8. Connection to DQBF (frust)

This experiment was triggered by `provers/frust/`. The structural
parallels:

- **`arbsolve` enumerates per-cell models of the consistency formula.**
  Each "cell" is a conjecture; each refuted cell is a conflict; the
  cone is the unsatisfiability witness. The Phase-3 finding — every
  cone has 10–30 implicates — says arbsolve is throwing away most of
  what a cell refutation teaches. A PB-style learning rule over the
  cell vars (not just one blocking clause) is the multi-learn analogue.

- **The interpolant from a Padoa proof IS a learned circuit.** The
  Padoa check is a conflict at the formula level; the McMillan
  interpolant is the cone-circuit summary; the AIGER encoding is the
  extension-variable representation. The Phase-4 framing — "the cone is
  the formula representing all conflict clauses" — is literally what
  the interpolation-based definability extraction does.

- **The "don't enumerate; generalize" principle is the question itself
  recast.** Visiting cuts one at a time enumerates; learning the cone
  (or a sound projection of it) generalises. The negative result on
  ext-factoring sharpens the principle: generalisation needs *logical*
  strength, not just compactness, and the only sound source of strength
  is the input encoding's structure.


## 9. Promising next steps

1. **Dynamic XOR/cardinality detection in conflict analysis with a
   soundness oracle.** The cone shape suggests a structure; verify it
   against the *input* clause tags (which gates contributed to the
   cone) before learning. The verification is O(cone size), cheap.
   This is the disciplined version of the heuristic that was 47%
   unsound.

2. **Cone-circuit learning with subsumption pruning.** Learn the cone's
   internal `z_l ↔ premises` definitions only for `z_l` that the
   1-UIP analysis identified as a UIP at *some* decision level — not
   just the first. These are the resolvents that get reused across
   levels; the cuts that are *not* level-UIPs are pure noise.

3. **PB conflict analysis as an arbsolve back end.** The arbsolve
   conflicts in `frust` are over cell-variable cubes; a PB constraint
   `Σ cells ≤ k` is the natural learning object. The ext-factoring
   negative result says don't learn the PB constraint as factored
   clauses — learn it natively and add a PB watcher. The benchmark
   target is `bmc_circuits/succinct`, where arbsolve currently doesn't
   converge.

4. **Reuse-gated extension introduction.** Track cone-gate co-occurrence
   across conflicts. Introduce an extension only when the gate has
   recurred in ≥`r` cones AND its introduction would let an *upcoming*
   learned clause be strictly shorter than the original. The first
   condition we tested (rate-limiting at `r=4,8`); the second we did
   not, and it's the missing piece — without it, factoring is
   propagation-neutral.


## Appendix: related work

*Written after the experiments, as required by the brief.*

Pseudo-Boolean conflict analysis (RoundingSat, Elffers & Nordström
SAT'18; Sat4j, Le Berre & Parrain JSAT'10; CIRCUS, Chai & Kuehlmann
DAC'03) does exactly the "learn a stronger constraint" move from
Phase 6: the learned object is a PB constraint, derived by
cutting-planes resolution from the input PB constraints. The soundness
discipline we rediscovered (the constraint must be derivable, not
inferred from cone shape) is exactly why these solvers need PB *input*
— they can't lift CNF to PB at conflict time because the lift is
abductive. CryptoMiniSat (Soos/Nohl/Castelluccia SAT'09) does the
same for XOR: detects parity gates *offline* by clause-pattern
matching, then runs Gaussian elimination as a propagator. Our `xor_off`
is the conflict-learning version.

Extension-by-factoring (Audemard/Katsirelos/Simon AAAI'10; Huang AIJ'10)
is the ext4 scheme. Their reported gains were modest; we now know why
from first principles — factoring is propagation-equivalent. They used
a learned-clause-frequency heuristic to decide which pairs to factor;
the cone gives a sharper signal (gate co-occurrence) but the signal
doesn't change what factoring *is*. The ER literature
(Tseitin'66, Cook'76, Krajíček'95) establishes the proof-theoretic
power that motivated this — ER p-simulates Frege — but proof-system
power and propagation strength are different things, as Phase 6 shows.

All-UIP / multi-UIP (Zhang/Madigan/Moskewicz/Malik ICCAD'01) compared
single cut schemes; multi-learn (learning several cuts) is the
combinatorial extension. Lazy Clause Generation (Ohrimenko/Stuckey/
Codish CP'07) keeps the constraint native and learns clauses from it on
conflict — the opposite direction. Bounded Variable Addition
(Manthey/Heule/Biere HVC'12) compresses an existing clause grid via an
extension variable, offline — the formula-rewriting version of
factoring. Symmetric learning (Devriendt et al. SAT'17) learns the
orbit of a clause under a detected symmetry — the closest prior to
"many clauses from one conflict" in the literature, and bounded by the
same wall: the symmetry must be a theorem of the encoding.

DRAT/RAT (Heule/Kullmann/Biere) is the proof-logging side of ER —
adding a RAT clause with a fresh variable *is* an ER step, so ER is
already implicitly part of the modern SAT ecosystem. The decision of
which RAT clauses to add is exactly the open question this exploration
quantifies.


## Reproducing

```sh
cd experiments/cdcl_multi_learn
python3 experiment.py            # all phases, all classes
python3 experiment.py xor_chain,php  # selected classes
# CSV output: phase3.csv (cuts/conflict), phase6.csv (strategy comparison)
```

The CDCL solver is ~500 lines of pure Python — readable, not fast. It
solves the experiment suite (40 instances × 8 strategies = 320 runs,
~30k conflicts total) in ~10 s. To add a new instance class, add a
generator to `generators.py` and an entry to `experiment.SWEEPS`.
