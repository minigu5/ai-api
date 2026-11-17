"""Snapshot a git working tree before the worker runs, so the report shows only this run's changes."""
import subprocess
from dataclasses import dataclass
from pathlib import Path


class NotARepo(Exception):
    pass


@dataclass
class Snapshot:
    root: Path
    base: str
    untracked: frozenset[str]


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def _untracked(root: Path) -> frozenset[str]:
    return frozenset(_git(root, "ls-files", "--others", "--exclude-standard").splitlines())


def snapshot(dir: Path) -> Snapshot:
    try:
        root = Path(_git(dir, "rev-parse", "--show-toplevel").strip())
    except (subprocess.CalledProcessError, FileNotFoundError, NotADirectoryError):
        raise NotARepo(f"{dir} is not a git working tree") from None
    # `git stash create` records the current edits as a commit without touching the tree.
    base = _git(root, "stash", "create").strip() or "HEAD"
    return Snapshot(root, base, _untracked(root))


def changes(s: Snapshot) -> tuple[str, list[str]]:
    stat = _git(s.root, "diff", "--stat", s.base).rstrip()
    return stat, sorted(_untracked(s.root) - s.untracked)
