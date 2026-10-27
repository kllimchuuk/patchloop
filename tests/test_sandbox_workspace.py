import pytest

from patchloop.sandbox import make_workspace, remove_workspace, workspace


def test_copy_skips_ignored_and_leaves_original(tmp_path):
    project = tmp_path / "proj"
    (project / ".git").mkdir(parents=True)
    (project / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    (project / ".venv").mkdir()
    (project / "pkg" / "__pycache__").mkdir(parents=True)
    (project / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")

    work = make_workspace(project, parent=tmp_path)

    assert (work / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 1\n"
    assert not (work / ".git").exists()
    assert not (work / ".venv").exists()
    assert not (work / "pkg" / "__pycache__").exists()
    (work / "pkg" / "mod.py").write_text("x = 2\n", encoding="utf-8")
    assert (project / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 1\n"


def test_symlinks_are_copied_as_links_not_followed(tmp_path):
    secret = tmp_path / "secret"
    secret.mkdir()
    (secret / "key").write_text("private", encoding="utf-8")
    project = tmp_path / "proj"
    project.mkdir()
    (project / "outside").symlink_to(secret)
    (project / "loop").symlink_to(project)
    (project / "dangling").symlink_to(tmp_path / "missing")

    work = make_workspace(project, parent=tmp_path)

    assert (work / "outside").is_symlink() and (work / "loop").is_symlink()
    assert (work / "dangling").is_symlink()


def test_workspace_is_removed_after_use(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    with workspace(project, parent=tmp_path) as work:
        assert work.is_dir()
    assert not work.exists()
    assert project.is_dir()


def test_remove_refuses_directories_it_did_not_create(tmp_path):
    lookalike = tmp_path / "patchloop-demo"  # a user project with the same prefix
    lookalike.mkdir()
    with pytest.raises(ValueError):
        remove_workspace(lookalike)
    assert lookalike.exists()


def test_env_files_are_left_out_by_default(tmp_path):
    project = tmp_path / "proj"
    (project / "sub").mkdir(parents=True)
    for name in (".env", ".env.local", "sub/.env", ".env.example"):
        (project / name).write_text("SECRET=1\n", encoding="utf-8")

    work = make_workspace(project, parent=tmp_path)
    assert not (work / ".env").exists() and not (work / ".env.local").exists()
    assert not (work / "sub" / ".env").exists()
    assert (work / ".env.example").exists()

    with_env = make_workspace(project, parent=tmp_path, copy_env=True)
    assert (with_env / ".env").exists() and (with_env / "sub" / ".env").exists()


def test_missing_project_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        make_workspace(tmp_path / "nope")
