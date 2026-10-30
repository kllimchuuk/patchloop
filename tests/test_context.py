import os

from patchloop.context.files import gather_context, local_imports
from patchloop.schemas import Failure

LIMITS = {"total_chars": 10_000, "max_file_chars": 1_000, "excerpt_lines": 2}


def _write(root, files):
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _fail(file, line=None):
    return Failure(kind="test", file=file, line=line, message="boom")


def test_imports_of_the_failing_test_are_followed_and_source_comes_first(tmp_path):
    _write(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/calc.py": "def add(a, b):\n    return a - b\n",
            "tests/test_calc.py": "from pkg.calc import add\n\ndef test_add():\n    pass\n",
        },
    )
    files = gather_context(tmp_path, [_fail("tests/test_calc.py", 4)], **LIMITS)
    assert [f.path for f in files] == ["pkg/calc.py", "tests/test_calc.py"]
    assert all(f.whole for f in files)


def test_import_forms(tmp_path):
    _write(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "",
            "pkg/b.py": "",
            "pkg/sub/__init__.py": "",
            "pkg/sub/c.py": "",
            "src/lib/d.py": "",
            "pkg/sub/main.py": "",
        },
    )
    text = (
        "import pkg.a\nfrom pkg import b\nfrom . import c\nfrom .. import b as bb\n"
        "import lib.d\nimport os\nfrom missing import nothing\n"
    )
    found = local_imports(tmp_path, "pkg/sub/main.py", text)
    assert set(found) == {
        "pkg/a.py",
        "pkg/__init__.py",
        "pkg/b.py",
        "pkg/sub/c.py",
        "pkg/sub/__init__.py",
        "src/lib/d.py",
    }


def test_a_syntax_error_in_the_failing_file_means_no_imports(tmp_path):
    assert local_imports(tmp_path, "a.py", "def f(:\n") == []


def test_missing_and_symlinked_files_are_skipped(tmp_path):
    secret = tmp_path / "secret.py"
    secret.write_text("TOKEN = 1\n", encoding="utf-8")
    work = tmp_path / "work"
    _write(work, {"ok.py": "x = 1\n"})
    os.symlink(secret, work / "link.py")
    files = gather_context(
        work, [_fail("gone.py"), _fail("link.py"), _fail("ok.py"), _fail(None)], **LIMITS
    )
    assert [f.path for f in files] == ["ok.py"]


def test_big_file_becomes_an_excerpt_around_the_failing_line(tmp_path):
    text = "".join(f"line {i}\n" for i in range(1, 400))
    _write(tmp_path, {"big.py": text})
    (f,) = gather_context(tmp_path, [_fail("big.py", 200)], **LIMITS)
    assert not f.whole
    assert f.text.splitlines() == [f"line {i}" for i in range(198, 203)]


def test_budget_is_respected(tmp_path):
    _write(tmp_path, {"a.py": "a" * 600, "b.py": "b" * 600})
    limits = {**LIMITS, "total_chars": 900}
    files = gather_context(tmp_path, [_fail("a.py"), _fail("b.py")], **limits)
    assert [(f.path, f.whole) for f in files] == [("a.py", True), ("b.py", False)]
    assert sum(len(f.text) for f in files) <= 900
