"""The gujtsr core must import without the heavy optional stack.

A QM skill sandbox installs requirements-skill.txt (13 packages, ~111 MB), not
requirements.txt (~623 MB). These tests fail if someone reintroduces a
module-level import that drags streamlit/fastapi/langchain/pandas into the
scrape or render path — which is not a style question: it broke a real minimal
install with `ModuleNotFoundError: No module named 'pandas'`, because
utils/__init__.py eagerly imported a pandas-backed helper.
"""
import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# Packages absent from requirements-skill.txt on purpose.
HEAVY = ["pandas", "streamlit", "fastapi", "uvicorn", "langchain_google_genai",
         "google.cloud", "selenium"]


def _import_in_subprocess(statement: str, blocked: list[str]) -> subprocess.CompletedProcess:
    """Run `statement` with `blocked` modules poisoned, so any import fails loudly."""
    guard = (
        "import sys\n"
        f"BLOCKED = {blocked!r}\n"
        "class _Blocker:\n"
        "    def find_module(self, name, path=None):\n"
        "        if any(name == b or name.startswith(b + '.') for b in BLOCKED):\n"
        "            raise ImportError('BLOCKED HEAVY IMPORT: ' + name)\n"
        "        return None\n"
        "sys.meta_path.insert(0, _Blocker())\n"
    )
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    return subprocess.run([sys.executable, "-c", guard + statement],
                          capture_output=True, text=True, cwd=REPO, env=env)


@pytest.mark.parametrize("module", ["gujtsr.fetch", "gujtsr.text", "gujtsr.render"])
def test_core_module_imports_without_the_heavy_stack(module):
    r = _import_in_subprocess(f"import {module}", HEAVY)
    assert r.returncode == 0, (
        f"{module} pulls in a heavy dependency:\n{r.stderr[-1500:]}")


def test_translation_imports_without_pandas_or_langchain():
    """utils/__init__ must stay lazy — this is the exact regression."""
    r = _import_in_subprocess(
        "from utils.json_translations import translate_to_gujarati as t;"
        "assert t('Bhavnagar', context='district') == 'ભાવનગર'",
        ["pandas", "langchain_google_genai"])
    assert r.returncode == 0, f"translation needs the heavy stack:\n{r.stderr[-1500:]}"


def test_requirements_skill_stays_lean():
    """Guard against requirements-skill.txt quietly growing back."""
    reqs = (REPO / "requirements-skill.txt").read_text().splitlines()
    pkgs = [l.split(">=")[0].split("==")[0].strip().lower()
            for l in reqs if l.strip() and not l.strip().startswith("#")]
    assert pkgs, "requirements-skill.txt has no packages"
    for banned in ("streamlit", "fastapi", "uvicorn", "pandas",
                   "selenium", "google-cloud-storage", "langchain"):
        assert not any(banned in p for p in pkgs), (
            f"{banned!r} is back in requirements-skill.txt — the skill sandbox does not need it")


def test_utils_init_has_no_eager_submodule_imports():
    """AST guard: utils/__init__.py must not import its submodules at module level."""
    tree = ast.parse((REPO / "utils" / "__init__.py").read_text())
    eager = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert not eager, (
        "utils/__init__.py imports at module level again: "
        f"{[getattr(n, 'module', None) for n in eager]}. Keep the PEP 562 __getattr__ "
        "so importing utils does not cost pandas.")
