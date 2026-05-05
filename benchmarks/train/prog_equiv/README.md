# prog_equiv — program equivalence with memory as a Skolem function

**Status: stub.** Encoding is wired end-to-end and the W=A=1 instance
is `core.semantics`-validated; the per-instruction step relation has
not been audited beyond that.

## Problem

Given two programs `P`, `Q` over a tiny register/memory ISA
([`tools/progequiv2dqbf/isa.py`](../../../tools/progequiv2dqbf/isa.py)),
decide whether they compute the same output register on every initial
memory image.

CBMC-style encodings unroll memory as one array per timestep
(`2^A · K` Booleans). This family instead encodes each program's
memory trace as a *single* Skolem function `mem(step, addr) → word`
and lets DQBF's Henkin semantics carry the "exists a trace" quantifier
over the function space directly. Instance size grows with
`log K + A`, not `2^A · K`.

## Bounded-trace encoding (`encode_bounded`)

Prefix:

    ∀ t, t', a, a' .
      ∃ memP(t,a), memP'(t',a'), regP(t), regP'(t'), pcP(t), pcP'(t'),
        memQ(t,a), memQ'(t',a'), regQ(t), regQ'(t'), pcQ(t), pcQ'(t'),
        Tseitin-aux(t, t', a, a')

Matrix:

    consistency   (t,a)==(t',a') → memX ↔ memX'   [tie copies to one fn]
                  t==t'          → regX/pcX ↔ regX'/pcX'
    shared input  t==0 → memP(0,a) ↔ memQ(0,a)
    init          t==0 → reg=0, pc=0
    step          t'==t+1: instruction at pcX(t) updates regX', pcX',
                  and memX' (frame axiom for un-stored addresses)
    equiv         haltedP ∧ haltedQ → regP[out] == regQ[out]

The two memory existentials per program have dependency sets `{t,a}`
and `{t',a'}` — incomparable, so this is genuine DQBF (not QBF).

**SAT** ⇒ `P ≡ Q` on every input within bound `K`.
**UNSAT** ⇒ either some input distinguishes `P` and `Q`, *or* one
program fails to reach `HALT` within `K` steps and the trace
constraints become unsatisfiable. The generator therefore emits each
pair at several bounds; "UNSAT at small K, SAT at large K" indicates a
bound artifact, not inequivalence.

## Inductive-coupling encoding (`encode_coupling`, stub)

Instead of bounding `K`, search for a **coupling invariant**
`Inv(state_P, state_Q) → bool` proving lock-step equivalence: if both
machines are in `Inv`-related states with equal memories, one joint
step keeps them `Inv`-related, and `Inv` implies output agreement at
joint halt. This is the relational-Hoare-logic / CHC view used by
Rêve-style equivalence checkers, lifted to DQBF.

The encoding builds the *product* transition system
`(state_P × state_Q × mem, T_P × T_Q, bad = halted∧halted∧out≠out)`
and feeds it to
[`tools.hwmc2dqbf_indinv.encode.encode_indinv`](../../../tools/hwmc2dqbf_indinv/encode.py).
**SAT** ⇒ coupling invariant found ⇒ `P ≡ Q` for *all* `K`.
**UNSAT** ⇒ no such Boolean invariant over (regs_P, regs_Q, pc_P, pc_Q)
— inconclusive (the witness may need to mention memory contents).

## Families

| pair                 | expected | note                                     |
|----------------------|----------|------------------------------------------|
| `swap_tmp`/`swap_xor`| sat      | classic; xor-swap ≡ tmp-swap             |
| `swap_tmp`/`swap_tmp`| sat      | self-pair sanity check                   |
| `sum_iter`/`sum_unroll`| unknown | only ≡ at N=2; iter loop is a stub       |
| `memcpy_fwd`/`memcpy_bwd`| unknown | placeholder programs (loops are stubs) |

Each pair × `(W, A, K)` grid; see `generate.py`.

## Related work

- Gitina et al., *Equivalence checking of partial designs using DQBF*
  (HVC'13) — the `pec_circuits` family in this repo; same prefix
  pattern but for combinational hardware rather than software.
- Lim et al., *Semantic Equivalence Checking of Decompiled Binaries*,
  CMU SEI 2022.
  https://www.sei.cmu.edu/annual-reviews/2022-research-review/semantic-equivalence-checking-of-decompiled-binaries/
  — a direct precedent for program-equivalence-via-SMT/SAT (binary
  lifted to IR, then equivalence-checked). Their array-theory memory
  model has one McCarthy `select/store` axiom per access; the encoding
  here is the natural DQBF lift: replace the array term with an
  explicit Skolem function `mem(t,a)` and let the dependency set
  enforce the read/write frame.
- Felsing et al., *Automating regression verification* (ASE'14, the
  Rêve tool) and Barthe et al. on product programs / relational Hoare
  logic — the basis for the inductive-coupling variant.
- This repo's `bmc_circuits_succinct` for the consistency-clause
  trick, and `tools/hwmc2dqbf_indinv` for the invariant prefix.
