"""AFL-008: CLI (executor stubbed; git behaviour in temporary repos)."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, ClassVar

import pytest

from fuzzer import cli
from fuzzer import fuzzer as fz
from fuzzer.executor import ExecResult

ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": "/dev/null"}


class Stub:
    """Replaces Executor; records every construction and run (target-never-executed checks)."""

    events: ClassVar[list[str]] = []

    def __init__(self, target: Path, timeout_s: float = 1.0) -> None:
        Stub.events.append("init")

    def run(self, data: bytes) -> ExecResult:
        Stub.events.append("run")
        return ExecResult(0, None, False, frozenset({1}), 0.001, b"")

    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fz, "Executor", Stub)
    Stub.events = []


@pytest.fixture(autouse=True)
def target(tmp_path: Path) -> Path:
    t = tmp_path / "tgt"
    t.write_text("#!/bin/sh\n")
    t.chmod(0o755)
    return t


@pytest.fixture
def seeds(tmp_path: Path) -> Path:
    d = tmp_path / "seeds"
    d.mkdir()
    (d / "S0").write_bytes(b"seed0")
    return d


def args(tmp: Path, seeds: Path | None, *extra: str) -> list[str]:
    a = ["--target", str(tmp / "tgt"), "--schedule", "uniform", "--seconds", "100",
         "--seed", "1", "--out", str(tmp / "out"), "--max-execs", "5", *extra]
    return a + ["--seeds", str(seeds)] if seeds else a


def run_json(tmp: Path) -> dict[str, Any]:
    return json.loads((tmp / "out/run.json").read_text())  # type: ignore[no-any-return]


def never_ran(capsys: pytest.CaptureFixture[str], tmp: Path, *needle: str) -> None:
    assert Stub.events == []
    err = capsys.readouterr().err
    assert all(n in err for n in needle) and "Traceback" not in err
    assert not (tmp / "out").exists() or not any((tmp / "out").iterdir())


def git(cwd: Path, *a: str) -> str:
    r = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True,
                       env={**os.environ, **ENV})
    return r.stdout.strip()


def test_run_writes_provenance(tmp_path: Path, seeds: Path) -> None:
    argv = args(tmp_path, seeds, "--timeout", "0.5")
    assert cli.main(argv) == 0
    j = run_json(tmp_path)
    assert j["argv"] == argv
    for k in ("config", "commit", "dirty", "python", "platform", "started_at", "seed_files",
              "freeze_commit"):
        assert k in j
    assert j["freeze_commit"] is None
    assert (tmp_path / "out/metrics.csv").exists()


def test_config_mapping(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, seeds: Path) -> None:
    got: list[fz.FuzzConfig] = []
    monkeypatch.setattr(fz, "run", got.append)
    cli.main(args(tmp_path, seeds, "--timeout", "0.5"))
    c = got[0]
    assert (c.max_execs, c.timeout_s, c.seed, c.seconds, c.schedule) == (5, 0.5, 1, 100.0, "uniform")
    assert c.out_dir == tmp_path / "out" and c.seeds_dir == seeds
    cli.main(["--target", str(tmp_path / "tgt"), "--schedule", "fast", "--seconds", "1", "--seed", "2",
              "--out", str(tmp_path / "o2"), "--seeds", str(seeds)])
    assert (got[1].max_execs, got[1].timeout_s, got[1].schedule) == (None, 1.0, "fast")


def test_bad_schedule_exits_nonzero(tmp_path: Path, seeds: Path) -> None:
    a = args(tmp_path, seeds)
    a[a.index("--schedule") + 1] = "slow"
    with pytest.raises(SystemExit) as e:
        cli.main(a)
    assert e.value.code == 2 and Stub.events == []


def test_default_seeds_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    got: list[fz.FuzzConfig] = []
    monkeypatch.setattr(fz, "run", got.append)
    d = tmp_path / "targets/seeds/tgt"
    d.mkdir(parents=True)
    (d / "S0").write_bytes(b"x")
    monkeypatch.chdir(tmp_path)
    cli.main(args(tmp_path, None))
    assert got[0].seeds_dir == Path("targets/seeds/tgt")


@pytest.mark.parametrize("kind", ["missing", "empty", "ds_store", "subdir"])
def test_bad_seeds_dir(kind: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    d = tmp_path / "sd"
    if kind != "missing":
        d.mkdir()
    if kind == "ds_store":
        (d / ".DS_Store").write_bytes(b"x")
    if kind == "subdir":
        (d / "sub").mkdir()
    assert cli.main(args(tmp_path, d)) != 0
    never_ran(capsys, tmp_path, str(d))


def test_seed_files_dsstore_and_subdir(tmp_path: Path, seeds: Path) -> None:
    (seeds / ".DS_Store").write_bytes(b"junk")
    (seeds / "sub").mkdir()
    assert cli.main(args(tmp_path, seeds)) == 0
    assert run_json(tmp_path)["seed_files"] == [
        {"name": "S0", "sha256": hashlib.sha256(b"seed0").hexdigest()}]


def test_seed_files_sorted(tmp_path: Path) -> None:
    d = tmp_path / "sd"
    d.mkdir()
    (d / "b").write_bytes(b"2")
    (d / "a").write_bytes(b"1")
    assert cli.main(args(tmp_path, d)) == 0
    assert [f["name"] for f in run_json(tmp_path)["seed_files"]] == ["a", "b"]


@pytest.mark.parametrize(("flag", "name"), [
    ("--max-execs", "max_execs"), ("--seconds", "seconds"), ("--timeout", "timeout_s")])
def test_invalid_params(flag: str, name: str, tmp_path: Path, seeds: Path,
                        capsys: pytest.CaptureFixture[str]) -> None:
    a = args(tmp_path, seeds)
    if flag in a:
        a[a.index(flag) + 1] = "0"
    else:
        a += [flag, "0"]
    assert cli.main(a) != 0
    never_ran(capsys, tmp_path, name)


@pytest.mark.parametrize("kind", ["missing", "not_exec"])
def test_bad_target(kind: str, tmp_path: Path, seeds: Path, target: Path,
                    capsys: pytest.CaptureFixture[str]) -> None:
    if kind == "missing":
        target.unlink()
    else:
        target.chmod(0o644)
    assert cli.main(args(tmp_path, seeds)) != 0
    never_ran(capsys, tmp_path, str(target))


def test_nonempty_out_is_error(tmp_path: Path, seeds: Path,
                               capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep").write_text("x")
    assert cli.main(args(tmp_path, seeds)) != 0
    assert Stub.events == [] and [p.name for p in out.iterdir()] == ["keep"]
    assert str(out) in capsys.readouterr().err


def test_empty_out_accepted(tmp_path: Path, seeds: Path) -> None:
    (tmp_path / "out").mkdir()
    assert cli.main(args(tmp_path, seeds)) == 0


# ---- git: dirty / commit / freeze-commit ----------------------------------------------

@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    git(r, "init", "-q", "-b", "main")
    (r / "f").write_text("1")
    git(r, "add", "f")
    git(r, "commit", "-qm", "c1")
    monkeypatch.chdir(r)
    return r


def go(tmp: Path, seeds: Path, *extra: str) -> int:
    """One CLI run into a fresh --out."""
    shutil.rmtree(tmp / "out", ignore_errors=True)
    return cli.main(args(tmp, seeds, *extra))


def test_dirty_states(repo: Path, tmp_path: Path, seeds: Path) -> None:
    assert go(tmp_path, seeds) == 0
    j = run_json(tmp_path)
    assert j["dirty"] is False and j["commit"] == git(repo, "rev-parse", "HEAD")
    (repo / "untracked").write_text("x")
    assert go(tmp_path, seeds) == 0
    assert run_json(tmp_path)["dirty"] is False
    (repo / "f").write_text("2")
    assert go(tmp_path, seeds) == 0
    assert run_json(tmp_path)["dirty"] is True


def test_outside_repo_dirty_null(tmp_path: Path, seeds: Path,
                                 monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert go(tmp_path, seeds) == 0
    j = run_json(tmp_path)
    assert j["dirty"] is None and j["commit"] == "unknown"


def test_git_missing_dirty_null(tmp_path: Path, seeds: Path,
                                monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "")
    assert go(tmp_path, seeds) == 0
    j = run_json(tmp_path)
    assert j["dirty"] is None and j["commit"] == "unknown"


def test_freeze_commit_ancestor_abbreviated(repo: Path, tmp_path: Path, seeds: Path) -> None:
    c1 = git(repo, "rev-parse", "HEAD")
    (repo / "f").write_text("2")
    git(repo, "commit", "-qam", "c2")
    assert go(tmp_path, seeds, "--freeze-commit", c1[:8]) == 0
    assert run_json(tmp_path)["freeze_commit"] == c1 and len(c1) == 40


@pytest.mark.parametrize("kind", ["missing", "side", "empty"])
def test_freeze_commit_rejected(kind: str, repo: Path, tmp_path: Path, seeds: Path,
                                capsys: pytest.CaptureFixture[str]) -> None:
    h = "" if kind == "empty" else "deadbeef"
    if kind == "side":
        git(repo, "checkout", "-qb", "side")
        (repo / "g").write_text("s")
        git(repo, "add", "g")
        git(repo, "commit", "-qm", "side")
        h = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "-q", "main")
    assert go(tmp_path, seeds, "--freeze-commit", h) != 0
    never_ran(capsys, tmp_path, h)


def test_module_help() -> None:
    root = Path(__file__).parent.parent
    r = subprocess.run([sys.executable, "-m", "fuzzer.cli", "--help"], check=False,
                       capture_output=True, cwd=root, env={**os.environ, "PYTHONPATH": "src"})
    assert r.returncode == 0
