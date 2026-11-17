"""Snapshot a git working tree before the worker runs, so the report shows only this run's changes."""
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


class NotARepo(Exception):
    pass


@dataclass
class Snapshot:
    root: Path
    tree: str


def _git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout


def _tree(root: Path) -> str:
    """Hash the whole working tree (tracked and untracked, minus ignored files) without touching the real index."""
    real_index = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-path", "index").strip())
    with tempfile.TemporaryDirectory() as tmp:
        index = Path(tmp) / "index"
        if real_index.exists():
            shutil.copy(real_index, index)  # reuse cached file stats so unchanged files are not rehashed
        env = dict(os.environ, GIT_INDEX_FILE=str(index))
        _git(root, "add", "-A", env=env)
        return _git(root, "write-tree", env=env).strip()


def snapshot(dir: Path) -> Snapshot:
    try:
        root = Path(_git(dir, "rev-parse", "--show-toplevel").strip())
    except (subprocess.CalledProcessError, FileNotFoundError, NotADirectoryError):
        raise NotARepo(f"{dir} is not a git working tree") from None
    return Snapshot(root, _tree(root))


def changes(s: Snapshot) -> tuple[str, list[str]]:
    after = _tree(s.root)
    stat = _git(s.root, "diff", "--stat", s.tree, after).rstrip()
    new = _git(s.root, "diff", "--name-only", "--diff-filter=A", s.tree, after).splitlines()
    return stat, sorted(new)
