# benchmarks/valid/

Held back from the improvement loop but checked periodically during
development to catch over-fitting before touching `test/`. Same kinds
of families as `train/` — different seeds, different scale parameters,
plus a few hand-picked instances.

Populate by re-running each `train/<family>/generate.py` with a
disjoint seed range (e.g. seeds 5000–5019) into a sibling directory
here.
