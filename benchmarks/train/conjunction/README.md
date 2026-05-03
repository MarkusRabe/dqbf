# conjunction

Variable-disjoint conjunction of K source formulas drawn from
different `train/` families. Tests whether solvers detect that the
clause-variable graph has K connected components and solve each
independently.

Expected result: SAT iff every component is SAT; UNSAT if any
component is UNSAT.

Regenerate: `python -m benchmarks.train.conjunction.generate`.
