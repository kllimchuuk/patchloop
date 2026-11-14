"""`patchloop apply` (SPEC §10, decisions 29 and 30): real git in a temporary repository."""

import subprocess
from pathlib import Path

import pytest
from support.projects import write_files
from typer.testing import CliRunner

from patchloop import runs
from patchloop.cli import app
from patchloop.patching import make_diff
from patchloop.runs import ApplyError, RunRecord, apply_record, save_record
from patchloop.schemas import GeneratedTest, RunResult

RUN_ID = "20261114-153042-a3f9"
BRANCH = f"patchloop/{RUN_ID}"
runner = CliRunner()


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo, capture_output=True, text=True, check=True,
    )
    return out.stdout


def make_repo(root: Path, files: dict[str, str]) -> Path:
    write_files(root, files)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "init")
    return root


def diff_between(tmp_path: Path, before: dict[str, str], after: dict[str, str]) -> str:
    old = write_files(tmp_path / "old", before)
    new = write_files(tmp_path / "new", {**before, **after})
    return make_diff(old, new, after)


def record_for(project: Path, diff: str, status="fixed", **result) -> RunRecord:
    return RunRecord(
        run_id=RUN_ID,
        project=str(project),
        result=RunResult(status=status, diff=diff, **result),
    )


BEFORE = {"pkg/calc.py": "def add(a, b):\n    return a - b\n", "README.md": "hi\n"}
AFTER = {"pkg/calc.py": "def add(a, b):\n    return a + b\n"}


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path / "proj", BEFORE)


@pytest.fixture
def diff(tmp_path):
    return diff_between(tmp_path, BEFORE, AFTER)


def branches(repo):
    return git(repo, "branch", "--list", "--format=%(refname:short)").split()


def test_a_clean_repo_gets_the_branch_and_an_unstaged_unchanged_head_change(repo, diff):
    head = git(repo, "rev-parse", "HEAD")
    changed = apply_record(record_for(repo, diff))
    assert changed == ["pkg/calc.py"]
    assert git(repo, "branch", "--show-current").strip() == BRANCH
    assert (repo / "pkg/calc.py").read_text() == AFTER["pkg/calc.py"]
    assert git(repo, "rev-parse", "HEAD") == head  # no commit
    assert git(repo, "diff", "--cached", "--name-only") == ""  # nothing staged
    assert git(repo, "status", "--porcelain").strip() == "M pkg/calc.py"


def test_a_new_file_and_a_file_without_a_trailing_newline(tmp_path):
    before = {"a.py": "x = 1", "keep.txt": "k\n"}
    after = {"a.py": "x = 2", "pkg/new.py": "y = 1\n"}
    repo = make_repo(tmp_path / "p", before)
    changed = apply_record(record_for(repo, diff_between(tmp_path, before, after)))
    assert sorted(changed) == ["a.py", "pkg/new.py"]
    assert (repo / "a.py").read_text() == "x = 2"
    assert (repo / "pkg/new.py").read_text() == "y = 1\n"


def test_the_generated_test_is_never_written_to_the_project(repo, diff):
    test = GeneratedTest(path="tests/test_patchloop_generated.py", content="x", output="y")
    apply_record(record_for(repo, diff, generated_test=test))
    assert not (repo / "tests").exists()
    assert "tests" not in git(repo, "status", "--porcelain")


def test_a_project_inside_a_bigger_repository(tmp_path):
    outer = make_repo(tmp_path / "outer", {f"sub/{n}": t for n, t in BEFORE.items()})
    project = outer / "sub"
    apply_record(record_for(project, diff_between(tmp_path, BEFORE, AFTER)))
    assert (project / "pkg/calc.py").read_text() == AFTER["pkg/calc.py"]
    assert git(outer, "status", "--porcelain").strip() == "M sub/pkg/calc.py"


def refused(repo, diff, match, **kw):
    def state():
        return git(repo, "status", "--porcelain"), branches(repo), git(repo, "rev-parse", "HEAD")

    before = state()
    with pytest.raises(ApplyError, match=match):
        apply_record(record_for(repo, diff, **kw))
    assert state() == before


def test_a_dirty_tracked_file_is_refused(repo, diff):
    (repo / "README.md").write_text("changed\n")
    refused(repo, diff, "not clean")


def test_an_untracked_file_counts_as_dirty(repo, diff):
    (repo / "scratch.txt").write_text("x")
    refused(repo, diff, "not clean")


def test_not_a_git_repository_is_refused(tmp_path, diff):
    write_files(tmp_path / "plain", BEFORE)
    with pytest.raises(ApplyError, match="git"):
        apply_record(record_for(tmp_path / "plain", diff))


def test_an_existing_branch_is_refused(repo, diff):
    git(repo, "branch", BRANCH)
    refused(repo, diff, "already exists")


def test_an_empty_diff_is_refused(repo):
    refused(repo, "", "no diff", status="not_fixed")


def test_a_diff_that_no_longer_fits_leaves_no_branch_behind(repo, diff):
    (repo / "pkg/calc.py").write_text("def add(a, b):\n    return 0\n")
    git(repo, "commit", "-qam", "someone else edited it")
    refused(repo, diff, "does not apply")
    assert branches(repo) == ["main"]


@pytest.mark.parametrize(
    "bad",
    ["../outside.py", "/etc/passwd", "a/../../x", ".git/config", ".GIT/config", "d/.Git/x"],
)
def test_a_path_outside_the_project_is_refused_before_git_runs(repo, bad, monkeypatch):
    evil = f"--- /dev/null\n+++ b/{bad}\n@@ -0,0 +1 @@\n+x\n"
    monkeypatch.setattr(runs, "_git", lambda *a, **k: pytest.fail("git must not run"))
    with pytest.raises(ApplyError, match="path"):
        apply_record(record_for(repo, evil))


def test_a_removed_line_that_looks_like_a_header_is_not_taken_for_one(tmp_path):
    before = {"q.sql": "-- old comment\nselect 1;\n"}
    after = {"q.sql": "select 1;\n"}
    repo = make_repo(tmp_path / "p", before)
    diff = diff_between(tmp_path, before, after)
    assert "--- old comment" in diff
    assert apply_record(record_for(repo, diff)) == ["q.sql"]
    assert (repo / "q.sql").read_text() == "select 1;\n"


@pytest.mark.parametrize(
    "extra",
    ["diff --git a/x b/../y\n", "rename from a\n", "new file mode 100755\n", "GIT binary patch\n"],
)
def test_git_extensions_in_the_diff_are_refused(repo, diff, extra, monkeypatch):
    monkeypatch.setattr(runs, "_git", lambda *a, **k: pytest.fail("git must not run"))
    with pytest.raises(ApplyError, match="unexpected line"):
        apply_record(record_for(repo, extra + diff))


def test_a_failing_rollback_does_not_hide_the_original_error(repo, diff, monkeypatch):
    real = runs._git

    def flaky(project, *args, **kw):
        if args[:1] == ("apply",) and "--check" not in args or args[:2] in (
            ("switch", "main"), ("branch", "-D")
        ):
            raise ApplyError("git hung")
        return real(project, *args, **kw)

    monkeypatch.setattr(runs, "_git", flaky)
    with pytest.raises(ApplyError, match="git hung") as info:
        apply_record(record_for(repo, diff))
    assert "rollback" in str(info.value)  # says that the branch may be left behind


def test_a_failure_after_the_branch_was_created_puts_everything_back(repo, diff, monkeypatch):
    real = runs._git

    def flaky(project, *args, **kw):
        if args[:1] == ("apply",) and "--check" not in args:
            raise ApplyError("disk full")
        return real(project, *args, **kw)

    monkeypatch.setattr(runs, "_git", flaky)
    with pytest.raises(ApplyError, match="disk full"):
        apply_record(record_for(repo, diff))
    assert git(repo, "branch", "--show-current").strip() == "main"
    assert branches(repo) == ["main"]


# ---- the command ------------------------------------------------------------------------------


@pytest.fixture
def stored(tmp_path, repo, diff):
    runs_dir = tmp_path / "runs"
    config = tmp_path / "patchloop.yml"
    config.write_text(f"runs_dir: {runs_dir}\n", encoding="utf-8")

    def store(status="fixed", **result):
        save_record(runs_dir, record_for(repo, diff, status=status, **result))

    store.config = config
    return store


def test_the_command_applies_a_stored_run_and_points_at_git_diff(stored, repo):
    stored()
    out = runner.invoke(app, ["apply", RUN_ID, "--config", str(stored.config)])
    assert out.exit_code == 0, out.output
    assert BRANCH in out.output and "pkg/calc.py" in out.output and "git diff" in out.output
    assert git(repo, "branch", "--show-current").strip() == BRANCH


def test_a_partial_fix_is_applied_with_a_warning(stored, repo):
    stored(status="partially_fixed", stop_reason="iteration_limit")
    out = runner.invoke(app, ["apply", RUN_ID, "--config", str(stored.config)])
    assert out.exit_code == 0 and "partial" in out.output.lower()
    assert git(repo, "branch", "--show-current").strip() == BRANCH


def test_the_command_reports_errors_without_a_traceback(stored, repo):
    stored()
    git(repo, "branch", BRANCH)
    out = runner.invoke(app, ["apply", RUN_ID, "--config", str(stored.config)])
    assert out.exit_code == 2 and "already exists" in out.output


def test_an_unknown_run_and_a_bad_id_are_errors(stored):
    for run_id in ["20200101-000000-ffff", "../x"]:
        out = runner.invoke(app, ["apply", run_id, "--config", str(stored.config)])
        assert out.exit_code == 2 and "Traceback" not in out.output


def test_the_git_timeout_comes_from_the_caller_not_a_literal(repo, diff, monkeypatch):
    seen = []
    real = subprocess.run

    def spy(*args, **kwargs):
        seen.append(kwargs["timeout"])
        return real(*args, **kwargs)

    monkeypatch.setattr(runs.subprocess, "run", spy)
    apply_record(record_for(repo, diff), git_timeout_s=7.0)
    assert seen and set(seen) == {7.0}


def test_a_form_feed_in_a_file_does_not_break_the_diff(tmp_path):
    before = {"m.py": "x = 1\n\x0c\ny = 2\n"}
    after = {"m.py": "x = 1\n\x0c\ny = 3\n"}
    repo = make_repo(tmp_path / "p", before)
    diff = diff_between(tmp_path, before, after)
    assert "No newline" not in diff
    apply_record(record_for(repo, diff))
    assert (repo / "m.py").read_text() == after["m.py"]
