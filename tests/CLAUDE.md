# tests/

- `unit/` — per-module pytest. Fast; runs on every commit.
- `integration/` — end-to-end SAT/UNSAT oracle suite (cadet-style).
  Slower; gated behind `pytest -m integration` and run in CI nightly.

Shared fixtures live in `conftest.py` (tmp dirs, tiny DQDIMACS builders,
a stub SAT oracle).
