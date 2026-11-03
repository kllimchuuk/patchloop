"""Throw-away projects built in `tmp_path`, shared by the tests that need files on disk."""

from pathlib import Path

BUGGY_CALC = {
    "requirements.txt": "",
    "pkg/__init__.py": "",
    "pkg/calc.py": "def add(a, b):\n    return a - b\n",
    "tests/test_calc.py": (
        "from pkg.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    ),
}


def write_files(root: Path, files: dict[str, str]) -> Path:
    """Create `files` (relative path -> text) under `root`, parents included."""
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def make_buggy_project(root: Path) -> Path:
    """A tiny project whose only test fails because `add` subtracts."""
    return write_files(root, BUGGY_CALC)
