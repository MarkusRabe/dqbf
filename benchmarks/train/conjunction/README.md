# conjunction

Variable-disjoint conjunction of K source formulas drawn from
different `train/` families. Tests whether solvers detect that the
clause-variable graph has K connected components and solve each
independently.

**Encoding.** K source instances are variable-renamed onto disjoint
ranges and their clauses concatenated; the prefix is the disjoint
union of the K prefixes. No shared variable means the matrix's
clause-variable graph has K connected components.

**SAT** iff every component is SAT; **UNSAT** if any is UNSAT.
`expected` is set by construction from the components' manifests.

**What it measures.** Decomposition: a solver that detects connected
components solves in `Σ tᵢ`; one that doesn't may pay `Π` (e.g.
expansion over the union of universals). Compare a DQBF solver's
runtime on the conjunction vs the sum of its parts.

**Compare against.** SAT preprocessors (SatELite-style variable-graph
splitting) and HQSpre — the standard QBF preprocessor with a
decomposition pass.

**Literature.** Biere, *Preprocessing and Inprocessing Techniques in
SAT* (Handbook of Satisfiability, 2nd ed.); Wimmer–Scholl et al.,
*HQSpre — Effective Preprocessing for QBF and DQBF* (TACAS'17).

Regenerate: `python -m benchmarks.train.conjunction.generate`.
