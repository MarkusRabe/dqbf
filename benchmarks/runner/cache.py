"""Content-addressed result cache for the multi-solver runner.

A run of `(solver-binary, instance, timeout)` is deterministic, so its
result can be reused as long as none of the three change. The cache key
is the SHA-256 of:

  - the solver binary's bytes (or, for `python -m pkg`, the package's
    source files), so a rebuild invalidates;
  - the gunzipped instance content, so a regenerated instance with the
    same path but different bytes invalidates;
  - the timeout, so a 5 s result isn't reused for a 10 s budget.

Only the `RunRow` is cached, not certificate files. `cert_status` is
preserved (it was checked once) but `cert_path` is cleared on a hit
because the certdir may have been wiped.

**Never clear `results/.bench_cache/`.** Keys are content-addressed,
so a rebuilt binary or regenerated instance is a new key — old entries
are simply unreferenced, not stale. If a result looks wrong, the bug
is in the binary that produced it (and that binary's hash will never
recur), not in the cache. Clearing throws away ~1h of unchanged-solver
results for nothing.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

CACHE_DIR = Path("results/.bench_cache")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:24]


def solver_hash(cmd: list[str], input_mapper_version: int = 0) -> str:
    """Hash the executable + non-templated args of a solver invocation.
    Two solvers sharing one binary (e.g. `abc -q 'bmc3 ...'` vs
    `abc -q 'pdr ...'`) must not collide. `input_mapper_version` lets
    `_run_one` invalidate scoped subsets when its file-mapping logic
    changes for a particular input_format (e.g. when on-the-fly
    `.dqdimacs`→`.qdimacs` conversion was added; bumping for `qdimacs`
    only)."""
    h = hashlib.sha256()
    if input_mapper_version:
        h.update(f"m{input_mapper_version}|".encode())
    # Args after the executable: distinguishes `abc -q bmc3` from
    # `abc -q pdr`. Placeholders ({file}, {timeout}) are identical
    # across solvers, so including them is harmless.
    h.update("|".join(cmd[1:]).encode())
    exe = cmd[0]
    p = Path(exe)
    if p.is_file():
        h.update(p.read_bytes())
    elif exe.endswith("python") or exe.endswith("python3"):
        # `python -m pkg.mod ...` — hash the package's .py sources.
        try:
            i = cmd.index("-m")
            mod = cmd[i + 1]
            import importlib.util

            spec = importlib.util.find_spec(mod)
            if spec and spec.origin:
                root = Path(spec.origin).parent
                for src in sorted(root.rglob("*.py")):
                    h.update(src.read_bytes())
        except (ValueError, IndexError, ImportError):
            h.update(repr(cmd).encode())
    else:
        h.update(repr(cmd).encode())
    return h.hexdigest()[:24]


def instance_hash(path: Path) -> str:
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    return _sha(raw)


def key(shash: str, ihash: str, timeout_s: float, verifier_v: int = 0) -> str:
    return _sha(f"{shash}|{ihash}|{timeout_s:.3f}".encode())


def load(k: str) -> dict | None:
    p = CACHE_DIR / f"{k}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def store(k: str, row: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{k}.json").write_text(json.dumps(row))


def backfill(jsonl_path: Path, timeout_s: float) -> tuple[int, int]:
    """Seed the cache from an existing run's JSONL. Hashes the binaries
    currently in the registry, so only valid when the binaries haven't
    changed since that run. Returns (stored, skipped)."""
    from benchmarks.runner.solvers import registry

    reg = registry()
    shash = {n: solver_hash(sv.cmd) for n, sv in reg.items() if sv.available}
    stored = skipped = 0
    for ln in jsonl_path.read_text().splitlines():
        if not ln.strip():
            continue
        r = json.loads(ln)
        sv = r["solver"]
        p = Path(r["path"])
        if sv not in shash or not p.exists():
            skipped += 1
            continue
        k = key(shash[sv], instance_hash(p), timeout_s)
        r.setdefault("cached", False)
        store(k, r)
        stored += 1
    return stored, skipped
