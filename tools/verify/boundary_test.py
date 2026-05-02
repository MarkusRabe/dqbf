"""Guard: verifier production code is fully self-contained.

Fails if any non-test file under tools/verify/ imports anything other
than stdlib, `tools.verify.*`, or the whitelisted external solver
packages.
"""

import ast
import sys
from pathlib import Path

VERIFY = Path(__file__).parent
ALLOWED_EXTERNAL = {"click", "pysat"}


def _stdlib(top: str) -> bool:
    return top in sys.stdlib_module_names


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
        elif isinstance(node, ast.Import):
            mods += [a.name for a in node.names]
    return mods


def test_verifier_is_self_contained() -> None:
    bad: list[str] = []
    for src in VERIFY.glob("*.py"):
        if src.name.endswith("_test.py") or src.name == "__init__.py":
            continue
        for mod in _imports(src):
            top = mod.split(".")[0]
            if _stdlib(top):
                continue
            if mod.startswith("tools.verify"):
                continue
            if top in ALLOWED_EXTERNAL:
                continue
            bad.append(f"{src.name}: imports {mod}")
    assert not bad, "tools/verify/ must be self-contained:\n  " + "\n  ".join(bad)
