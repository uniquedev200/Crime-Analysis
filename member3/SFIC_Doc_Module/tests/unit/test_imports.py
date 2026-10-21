"""Gate 0 import boundary tests using AST inspection."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


def _find_py_files(directory: Path) -> list[Path]:
    """Recursively list all .py files in a directory."""
    if not directory.exists():
        return []
    return [p for p in directory.rglob("*.py") if p.is_file()]


def _check_forbidden_imports(
    py_files: list[Path],
    forbidden_prefixes: list[str],
) -> list[str]:
    """Scan Python files via AST and return list of violation descriptions."""
    violations: list[str] = []

    for file_path in py_files:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    for prefix in forbidden_prefixes:
                        if name == prefix or name.startswith(prefix + "."):
                            violations.append(f"{file_path.name}:{node.lineno} imports forbidden '{name}'")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                # Check module itself
                for prefix in forbidden_prefixes:
                    if module == prefix or module.startswith(prefix + "."):
                        violations.append(f"{file_path.name}:{node.lineno} imports from forbidden module '{module}'")
                # Check imported symbols (e.g. from atlas.ports import entity_store)
                for alias in node.names:
                    full_name = f"{module}.{alias.name}" if module else alias.name
                    for prefix in forbidden_prefixes:
                        if full_name == prefix or full_name.startswith(prefix + "."):
                            violations.append(f"{file_path.name}:{node.lineno} imports forbidden symbol '{full_name}'")

    return violations


@pytest.mark.gate0
def test_llm_no_resolve_import() -> None:
    worktree = Path(__file__).resolve().parent.parent.parent
    llm_dir = worktree / "src" / "atlas" / "llm"
    py_files = _find_py_files(llm_dir)
    assert len(py_files) > 0, "No Python files found under src/atlas/llm"

    forbidden = [
        "atlas.resolve",
        "resolve",
        "atlas.adapters",
        "adapters",
    ]
    violations = _check_forbidden_imports(py_files, forbidden)
    assert not violations, f"LLM boundary violation(s) detected: {violations}"


@pytest.mark.gate0
def test_llm_no_entity_store_import() -> None:
    worktree = Path(__file__).resolve().parent.parent.parent
    llm_dir = worktree / "src" / "atlas" / "llm"
    py_files = _find_py_files(llm_dir)
    assert len(py_files) > 0, "No Python files found under src/atlas/llm"

    forbidden = [
        "atlas.ports.entity_store",
        "ports.entity_store",
    ]
    violations = _check_forbidden_imports(py_files, forbidden)
    assert not violations, f"LLM entity_store boundary violation(s) detected: {violations}"
