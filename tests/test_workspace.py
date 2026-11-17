import subprocess

import pytest

from local_agent.workspace import NotARepo, changes, snapshot


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "a.py").write_text("a = 1\n")
    (tmp_path / "b.py").write_text("b = 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return tmp_path


def test_not_a_repo(tmp_path):
    with pytest.raises(NotARepo):
        snapshot(tmp_path)


def test_clean_repo_changes(repo):
    s = snapshot(repo)
    (repo / "a.py").write_text("a = 2\n")
    (repo / "new.py").write_text("x\n")
    stat, new = changes(s)
    assert "a.py" in stat
    assert new == ["new.py"]


def test_dirty_repo_excludes_prior_edits(repo):
    (repo / "a.py").write_text("a = 99\n")
    (repo / "old.txt").write_text("old\n")
    s = snapshot(repo)
    (repo / "b.py").write_text("b = 2\n")
    stat, new = changes(s)
    assert "b.py" in stat and "a.py" not in stat
    assert new == []


def test_snapshot_does_not_touch_tree(repo):
    (repo / "a.py").write_text("a = 99\n")
    (repo / "old.txt").write_text("old\n")
    before = git(repo, "status", "--porcelain")
    snapshot(repo)
    assert git(repo, "status", "--porcelain") == before


def test_freshly_copied_repo(repo, tmp_path):
    """A copied checkout has a stale index; the first `git stash create` there exits 1."""
    import shutil
    copy = tmp_path / "copy"
    shutil.copytree(repo, copy, copy_function=shutil.copy)
    s = snapshot(copy)
    assert changes(s) == ("", [])
