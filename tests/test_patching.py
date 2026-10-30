import os

import pytest

from patchloop.patching import PatchError, apply_patch, make_diff, patch_hash
from patchloop.schemas import Patch


def test_normal_write(tmp_path):
    (tmp_path / "a.py").write_text("old\n", encoding="utf-8")
    patch = Patch(files={"a.py": "new\n", "pkg/sub/b.py": "x = 1\n"}, explanation="e")
    apply_patch(tmp_path, patch)
    assert (tmp_path / "a.py").read_text() == "new\n"
    assert (tmp_path / "pkg" / "sub" / "b.py").read_text() == "x = 1\n"


def test_newlines_and_unicode_are_written_as_given(tmp_path):
    apply_patch(tmp_path, Patch(files={"a.txt": "ž\r\nč\n"}, explanation="e"))
    assert (tmp_path / "a.txt").read_bytes() == "ž\r\nč\n".encode()


def test_symlinked_file_is_refused_and_target_untouched(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("keep\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    os.symlink(secret, work / "a.py")
    with pytest.raises(PatchError, match="symlink"):
        apply_patch(work, Patch(files={"a.py": "pwned\n"}, explanation="e"))
    assert secret.read_text() == "keep\n"


def test_symlinked_directory_is_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    os.symlink(outside, work / "pkg")
    with pytest.raises(PatchError, match="symlink"):
        apply_patch(work, Patch(files={"pkg/a.py": "x\n"}, explanation="e"))
    assert list(outside.iterdir()) == []


def test_a_bad_path_writes_nothing(tmp_path):
    (tmp_path / "dir").mkdir()
    patch = Patch(files={"good.py": "x\n", "dir": "y\n"}, explanation="e")
    with pytest.raises(PatchError, match="directory"):
        apply_patch(tmp_path, patch)
    assert not (tmp_path / "good.py").exists()


def test_lone_surrogate_is_not_valid_text(tmp_path):
    with pytest.raises(PatchError, match="valid text"):
        apply_patch(tmp_path, Patch(files={"a.py": "\ud800"}, explanation="e"))


def test_hash_ignores_order_and_explanation_but_not_content_or_split():
    a = Patch(files={"a.py": "1", "b.py": "2"}, explanation="one")
    b = Patch(files={"b.py": "2", "a.py": "1"}, explanation="two")
    assert patch_hash(a) == patch_hash(b)
    assert patch_hash(a) != patch_hash(Patch(files={"a.py": "1", "b.py": "3"}, explanation="x"))
    assert patch_hash(Patch(files={"a": "bc"}, explanation="x")) != patch_hash(
        Patch(files={"ab": "c"}, explanation="x")
    )
    assert len(patch_hash(a)) == 64


def _trees(tmp_path):
    original, changed = tmp_path / "orig", tmp_path / "work"
    original.mkdir()
    changed.mkdir()
    return original, changed


def test_diff_of_modified_and_new_files(tmp_path):
    original, changed = _trees(tmp_path)
    (original / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    (changed / "a.py").write_text("x = 1\ny = 3\n", encoding="utf-8")
    (changed / "new.py").write_text("z = 0\n", encoding="utf-8")
    diff = make_diff(original, changed, ["new.py", "a.py"])
    assert diff == (
        "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n x = 1\n-y = 2\n+y = 3\n"
        "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+z = 0\n"
    )


def test_unchanged_and_absent_files_are_left_out(tmp_path):
    original, changed = _trees(tmp_path)
    (original / "same.py").write_text("x\n", encoding="utf-8")
    (changed / "same.py").write_text("x\n", encoding="utf-8")
    assert make_diff(original, changed, ["same.py", "gone.py", "never.py"]) == ""


def test_missing_final_newline_is_marked(tmp_path):
    original, changed = _trees(tmp_path)
    (original / "a.txt").write_text("a", encoding="utf-8")
    (changed / "a.txt").write_text("b", encoding="utf-8")
    diff = make_diff(original, changed, ["a.txt"])
    assert diff.endswith("-a\n\\ No newline at end of file\n+b\n\\ No newline at end of file\n")


def test_diff_refuses_symlinks_and_binary_files(tmp_path):
    original, changed = _trees(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("token\n", encoding="utf-8")
    os.symlink(secret, changed / "a.py")
    with pytest.raises(PatchError, match="symlink"):
        make_diff(original, changed, ["a.py"])
    (changed / "b.bin").write_bytes(b"\xff\xfe\x00")
    with pytest.raises(PatchError, match="UTF-8"):
        make_diff(original, changed, ["b.bin"])


def test_restore_puts_files_back_and_removes_new_ones(tmp_path):
    from patchloop.patching import restore_files

    original, work = _trees(tmp_path)
    (original / "a.py").write_text("old\n", encoding="utf-8")
    (work / "a.py").write_text("patched\n", encoding="utf-8")
    (work / "pkg").mkdir()
    (work / "pkg" / "new.py").write_text("x\n", encoding="utf-8")
    restore_files(original, work, ["a.py", "pkg/new.py", "never.py"])
    assert (work / "a.py").read_text() == "old\n"
    assert not (work / "pkg" / "new.py").exists()


def test_restore_replaces_a_symlink_without_touching_its_target(tmp_path):
    from patchloop.patching import restore_files

    original, work = _trees(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("keep\n", encoding="utf-8")
    (original / "a.py").write_text("old\n", encoding="utf-8")
    os.symlink(secret, work / "a.py")
    restore_files(original, work, ["a.py"])
    assert (work / "a.py").read_text() == "old\n" and not (work / "a.py").is_symlink()
    assert secret.read_text() == "keep\n"


def test_restore_refuses_a_symlinked_directory(tmp_path):
    from patchloop.patching import restore_files

    original, work = _trees(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "new.py").write_text("keep\n", encoding="utf-8")
    os.symlink(outside, work / "pkg")
    with pytest.raises(PatchError, match="symlink"):
        restore_files(original, work, ["pkg/new.py"])
    assert (outside / "new.py").read_text() == "keep\n"
