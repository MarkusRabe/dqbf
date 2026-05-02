"""Guard: verifier production code imports only data formats.

Fails if any non-test file under tools/verify/ imports from `provers`,
or imports a private name (leading underscore) from `core.semantics`.
"""

import ast
from pathlib import Path

VERIFY = Path(__file__).parent
ALLOWED_TOP = {"core", "tools"}


def _imports(path: Path) -> list[tuple[str, list[str]]]:
    tree = ast.parse(path.read_text())
    out: list[tuple[str, list[str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.append((node.module, [a.name for a in node.names]))
        elif isinstance(node, ast.Import):
            for a in node.names:
                out.append((a.name, []))
    return out


def test_verifier_imports_only_data_formats() -> None:
    bad: list[str] = []
    for src in VERIFY.glob("*.py"):
        if src.name.endswith("_test.py") or src.name == "__init__.py":
            continue
        for mod, names in _imports(src):
            top = mod.split(".")[0]
            if top == "provers":
                bad.append(f"{src.name}: imports {mod}")
            if mod == "core.semantics":
                priv = [n for n in names if n.startswith("_")]
                if priv:
                    bad.append(f"{src.name}: imports private {priv} from core.semantics")
    assert not bad, "verifier trust boundary violated:\n  " + "\n  ".join(bad)
