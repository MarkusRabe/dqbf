# tests/

**End-to-end integration tests only.** Unit tests live next to the code
they test (`foo.py` → `foo_test.py` in the same directory) so they're
easy to find and move with the module.

- `integration/` — cadet-style SAT/UNSAT oracle suite. Slower; gated
  behind `pytest -m integration` and run in CI nightly.

`conftest.py` here holds fixtures shared across integration tests (tmp
dirs, tiny DQDIMACS builders, a stub SAT oracle).
