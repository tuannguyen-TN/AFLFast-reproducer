"""Tests for the tracked .githooks/commit-msg hook (AFL-015).

Runs real git in a temp repo via subprocess, with core.hooksPath set there only."""
import os
import subprocess
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent / ".githooks"


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo, capture_output=True, text=True, check=False,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    assert git(tmp_path, "init", "-q").returncode == 0
    assert git(tmp_path, "config", "core.hooksPath", str(HOOKS)).returncode == 0
    return tmp_path


def commit(repo: Path, msg: str) -> subprocess.CompletedProcess[str]:
    f = repo / "msg.txt"
    f.write_text(msg)
    return git(repo, "commit", "--allow-empty", "-q", "-F", str(f))


def test_hook_is_executable() -> None:
    assert os.access(HOOKS / "commit-msg", os.X_OK)


def test_no_id_rejected(repo: Path) -> None:
    r = commit(repo, "no ticket id\n")
    assert r.returncode != 0
    assert "ticket id" in r.stderr
    assert git(repo, "rev-parse", "HEAD").returncode != 0  # no commit created


def test_id_accepted(repo: Path) -> None:
    assert commit(repo, "AFL-123: msg\n").returncode == 0


def test_commented_id_does_not_count(repo: Path) -> None:
    # --cleanup=verbatim keeps the comment line in the file the hook sees
    f = repo / "msg.txt"
    f.write_text("no id\n# AFL-123\n")
    r = git(repo, "commit", "--allow-empty", "-q", "--cleanup=verbatim", "-F", str(f))
    assert r.returncode != 0
