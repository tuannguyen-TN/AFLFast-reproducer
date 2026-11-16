"""AFL-011: campaign runner (harness/run_campaign.py) and fuzzer CSV line buffering.

Tiny budgets on targets/bin/toy_parser; sysctl, the symbolizer, the executor and trial launch are
monkeypatched where a test is about the guard, not the trial.
"""
import csv
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from fuzzer.executor import ExecResult

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "harness"))
import run_campaign as rc

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": "/dev/null"}
needs_bin = pytest.mark.skipif(not (REPO / "targets/bin/toy_parser").exists(),
                               reason="targets/bin/toy_parser not built")
TOY_TRIGGERS = {"toy-1": "42554761", "toy-2": "21616161"}  # b"BUGa", b"!aaa" (AC "Trigger table")
METRICS_HEADER = ("elapsed_s,execs,edges,corpus_size,distinct_path_ids,crash_events,crashes_saved,"
                  "hangs,hang_time_s")


def metrics_row(execs: float = 1000, elapsed: float = 10.0, hangs: int = 0,
                hang_time: float = 0.0) -> str:
    return f"{elapsed},{execs},5,10,30,0,0,{hangs},{hang_time}"


def stub_launch(spec: Any) -> Any:
    """A `_launch` stub writing only metrics.csv; spec(trial) gives metrics_row kwargs, or None."""
    def fake(t: rc.Trial, cfg: rc.Cfg, r: Path, freeze: str | None) -> subprocess.CompletedProcess[str]:
        t.out.mkdir(parents=True)
        kw = spec(t)
        body = METRICS_HEADER + "\n" + (metrics_row(**kw) + "\n" if kw is not None else "")
        (t.out / "metrics.csv").write_text(body)
        return subprocess.CompletedProcess([], 0, "", "")
    return fake


def git(cwd: Path, *a: str) -> str:
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True,
                          env=ENV).stdout.strip()


def cfg_text(**over: Any) -> str:
    d: dict[str, Any] = {"trials_per_config": 10, "seconds_per_trial": 0.5, "base_seed": 7,
                         "timeout_s": 2.5, "concurrency": 3,
                         "targets": ["targets/bin/toy_parser"], "schedules": ["uniform", "fast"]}
    d.update(over)
    lines = []
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, list):
            lines += [f"{k}:"] + [f"  - {x}" for x in v]
        else:
            lines.append(f"{k}: {v}")
    return "\n".join(lines) + "\n"


@pytest.fixture(autouse=True)
def _clear_abort() -> None:
    rc._ABORT.clear()


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repo-shaped tmp tree: real binaries (symlink), copied S0s, bug tables, one config."""
    r = tmp_path / "repo"
    (r / "targets").mkdir(parents=True)
    (r / "experiments/configs").mkdir(parents=True)
    (r / "targets/bin").symlink_to(REPO / "targets/bin")
    shutil.copytree(REPO / "targets/seeds", r / "targets/seeds", ignore=shutil.ignore_patterns(".*"))
    shutil.copy(REPO / "targets/ground_truth.json", r / "targets/ground_truth.json")
    shutil.copy(REPO / "targets/triggers.json", r / "targets/triggers.json")
    (r / "experiments/configs/main.yaml").write_text(cfg_text())
    (r / ".gitignore").write_text("targets/bin\nresults/\n")
    monkeypatch.setattr(rc, "physical_cpus", lambda: 8)
    monkeypatch.setattr(rc, "_cmd", lambda a: subprocess.CompletedProcess(a, 1, "", ""))  # hermetic
    return r


@pytest.fixture
def clean_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Probes refuse a dirty or unknown tree (AFL-031 P3): a non-git tmp tree reads as clean."""
    monkeypatch.setattr(rc, "_provenance", lambda: ("unknown", False))


def to_git(r: Path) -> None:
    git(r, "init", "-q", "-b", "main")
    git(r, "add", ".")
    git(r, "commit", "-qm", "c1")


def go(r: Path, *args: str, cfg: str | None = None) -> int:
    if cfg is not None:
        (r / "experiments/configs/main.yaml").write_text(cfg)
    return rc.run(["experiments/configs/main.yaml", *args], root=r)


def no_trials(r: Path) -> bool:
    return not (r / "results").exists()


@pytest.fixture
def planned(monkeypatch: pytest.MonkeyPatch) -> list[rc.Trial]:
    """Stub execute: guards pass, trials are recorded, none runs."""
    seen: list[rc.Trial] = []

    def fake(kind: str, trials: list[rc.Trial], *a: Any) -> bool:
        seen.extend(trials)
        for t in trials:  # a completed pilot has a final row per trial (granularity decision)
            t.out.mkdir(parents=True)
            (t.out / "metrics.csv").write_text(METRICS_HEADER + "\n" + metrics_row() + "\n")
        return True
    monkeypatch.setattr(rc, "execute", fake)
    return seen


# ---- config, caps, seed ranges ---------------------------------------------------------------

def test_real_main_yaml_parses() -> None:
    cfg = rc.parse_config(rc.load_yaml(REPO / "experiments/configs/main.yaml"))
    assert [Path(t).name for t in cfg.targets] == ["toy_parser", "tlv_parser", "mini_format"]
    assert cfg.timeout_s > 0 and cfg.concurrency >= 1 and cfg.schedules == ("uniform", "fast")


def test_real_ranges_disjoint_and_caps_999_ok() -> None:
    cfg = rc.parse_config(rc.load_yaml(REPO / "experiments/configs/main.yaml"))
    names = ["toy_parser", "tlv_parser", "mini_format"]
    rc.check_disjoint(cfg, names)
    rc.check_caps(rc.Cfg(999, 1, 0, cfg.targets, cfg.schedules, 1.0, 5), names)
    sets = rc.seed_sets(cfg, names)
    assert sets["main"] == {1000 + i for i in range(10)} and sets["first_pilot"] == {2000, 2001, 2002}


def test_1000_trials_refused_no_dirs(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert go(root, "--allow-fewer-targets", "t", cfg=cfg_text(trials_per_config=1000)) == 2
    err = capsys.readouterr().err
    assert "main campaign" in err and "1000" in err and "cap" in err
    assert no_trials(root)


def test_overlapping_ranges_refused(root: Path, monkeypatch: pytest.MonkeyPatch,
                                    capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setitem(rc.SEED_OFFSETS, "probe", 1000)
    assert go(root, "--allow-fewer-targets", "t") == 2
    err = capsys.readouterr().err
    assert "'first_pilot'" in err and "'probe'" in err and "shared seed" in err
    assert no_trials(root)


@pytest.mark.parametrize("missing", ["timeout_s", "concurrency"])
def test_missing_key_refused(root: Path, missing: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert go(root, "--allow-fewer-targets", "t", cfg=cfg_text(**{missing: None})) == 2
    assert missing in capsys.readouterr().err and no_trials(root)


# ---- concurrency cap / sysctl ----------------------------------------------------------------

def _sysctl(monkeypatch: pytest.MonkeyPatch, out: str = "", rc_: int = 0, missing: bool = False,
            ) -> None:
    def fake(args: list[str]) -> subprocess.CompletedProcess[str]:
        if missing:
            raise FileNotFoundError(args[0])
        return subprocess.CompletedProcess(args, rc_, out, "")
    monkeypatch.setattr(rc, "_cmd", fake)


def test_concurrency_above_physicalcpu_refused(root: Path, monkeypatch: pytest.MonkeyPatch,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.undo()  # drop the fixture's physical_cpus stub
    monkeypatch.setattr(rc, "_launch", stub_launch(lambda t: {}))
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    _sysctl(monkeypatch, "2\n")
    assert go(root, "--allow-fewer-targets", "t", cfg=cfg_text(concurrency=3)) == 2
    err = capsys.readouterr().err
    assert "3" in err and "2" in err and no_trials(root)
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t",
              cfg=cfg_text(concurrency=2)) == 0


@pytest.mark.parametrize("kw", [{"out": "8\n", "rc_": 1}, {"missing": True}, {"out": ""},
                                {"out": "0"}, {"out": "abc"}, {"out": "-4"}, {"out": "4.5"}])
def test_unusable_sysctl_refused(root: Path, monkeypatch: pytest.MonkeyPatch, kw: dict[str, Any],
                                 capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.undo()
    if kw.get("rc_"):  # T2: a usable value with a failing exit: only the exit status can refuse
        assert kw["out"].strip().isdigit() and kw["rc_"] == 1
    _sysctl(monkeypatch, **kw)
    assert go(root, "--allow-fewer-targets", "t", cfg=cfg_text(concurrency=1)) == 2
    assert "sysctl -n hw.physicalcpu" in capsys.readouterr().err and no_trials(root)


def test_no_override_options_in_source() -> None:
    src = (REPO / "harness/run_campaign.py").read_text()
    opts = [ln for ln in src.splitlines() if "add_argument(" in ln]
    assert not [o for o in opts if any(w in o for w in ("skip", "force", "ignore", "no-check",
                                                        "cap", "symbolizer", "s0"))]
    assert "environ.get(" not in src.replace('os.environ.get("PYTHONPATH", "")', "")
    assert "merge-base" not in src and "rev-parse" not in src  # AC (c.i): shared helper only


# ---- targets ---------------------------------------------------------------------------------

def test_fewer_than_three_targets_refused_then_override_recorded(
        root: Path, planned: list[rc.Trial], monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    two = cfg_text(targets=["targets/bin/toy_parser", "targets/bin/tlv_parser"])
    assert go(root, "--kind", "first_pilot", cfg=two) == 2
    assert "PRD s8" in capsys.readouterr().err and no_trials(root) and not planned
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "AFL-016 late") == 0
    meta = json.loads((root / "results/pilot/first_pilot/campaign.json").read_text())
    assert meta["allow_fewer_targets"] == "AFL-016 late" and len(planned) == 3 * 2 * 2


def test_missing_binary_refused(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert go(root, "--allow-fewer-targets", "t",
              cfg=cfg_text(targets=["targets/bin/nope"])) == 2
    assert "nope" in capsys.readouterr().err and no_trials(root)


# ---- S0 pre-flight ---------------------------------------------------------------------------

def _s0_case(root: Path, how: str) -> None:
    d = root / "targets/seeds/toy_parser"
    sums = root / "targets/seeds/SHA256SUMS"
    if how == "missing":
        (d / "S0").unlink()
    elif how == "tampered":
        (d / "S0").write_bytes((d / "S0").read_bytes() + b"x")
    elif how == "no_line":
        sums.write_text("".join(ln + "\n" for ln in sums.read_text().splitlines()
                                if "toy_parser" not in ln))
    elif how == "no_sums":
        sums.unlink()
    elif how == "empty":
        (d / "S0").write_bytes(b"")
        import hashlib
        h = hashlib.sha256(b"").hexdigest()
        sums.write_text("".join(f"{h}  toy_parser/S0\n" if "toy_parser" in ln else ln + "\n"
                                for ln in sums.read_text().splitlines()))
    elif how == "stray":
        (d / "S1").write_bytes(b"a")


@pytest.mark.parametrize("how,word", [("missing", "S0"), ("tampered", "hash"),
                                      ("no_line", "toy_parser/S0"), ("no_sums", "SHA256SUMS"),
                                      ("empty", "empty"), ("stray", "S1")])
def test_s0_preflight_refusals(root: Path, how: str, word: str,
                               capsys: pytest.CaptureFixture[str]) -> None:
    _s0_case(root, how)
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t") == 2
    err = capsys.readouterr().err
    assert ("toy_parser" in err or how == "no_sums") and word in err and no_trials(root)


# ---- symbolizer pre-flight -------------------------------------------------------------------

def test_real_triggers_json_has_toy_entries() -> None:
    trig = json.loads((REPO / "targets/triggers.json").read_text())
    assert {k: trig[k] for k in TOY_TRIGGERS} == TOY_TRIGGERS


@needs_bin
def test_symbolizer_real_checks_every_bug(root: Path, planned: list[rc.Trial],
                                          capsys: pytest.CaptureFixture[str]) -> None:
    cfg = rc.parse_config(rc.load_yaml(root / "experiments/configs/main.yaml"))
    names = [Path(t).name for t in cfg.targets]
    gt = json.loads((root / "targets/ground_truth.json").read_text())
    want = sorted(b for b, e in gt.items() if e["target"] in names)  # from ground truth, not hard-coded
    assert want and sorted(rc.check_symbolizer(names, root, cfg.timeout_s)) == want
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t") == 0  # campaign proceeds
    assert planned and "symbolization" not in capsys.readouterr().err


@pytest.mark.parametrize("kind", ["first_pilot", "main"])
def test_symbolizer_failure_aborts(root: Path, kind: str, monkeypatch: pytest.MonkeyPatch,
                                   capsys: pytest.CaptureFixture[str]) -> None:
    to_git(root)

    class Fake:
        def __init__(self, t: Path, timeout_s: float) -> None: ...
        def run(self, data: bytes) -> ExecResult:
            return ExecResult(None, 6, False, frozenset(), 0.1, data)
        def close(self) -> None: ...
    monkeypatch.setattr(rc, "Executor", Fake)
    monkeypatch.setattr(rc, "crash_site", lambda err, src: (
        "no_target_frame" if err.hex() == TOY_TRIGGERS["toy-1"] else "scan"))
    extra = ["--freeze-commit", "HEAD"] if kind == "main" else []
    assert go(root, "--kind", kind, "--allow-fewer-targets", "t", *extra) == 2
    err = capsys.readouterr().err
    assert "symbolization" in err and "toy-1" in err and "toy-2" not in err and no_trials(root)


def test_trigger_missing_for_bug_names_bug_and_file(root: Path,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    (root / "targets/triggers.json").write_text(json.dumps({"toy-1": TOY_TRIGGERS["toy-1"]}))
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t") == 2
    err = capsys.readouterr().err
    assert "toy-2" in err and "targets/triggers.json" in err and no_trials(root)


# ---- git provenance --------------------------------------------------------------------------

def test_main_dirty_tree_refused_pilot_runs_dirty(root: Path, capsys: pytest.CaptureFixture[str],
                                                  planned: list[rc.Trial],
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    to_git(root)
    (root / ".gitignore").write_text("targets/bin\nresults/\n# dirty\n")
    assert go(root, "--allow-fewer-targets", "t", "--freeze-commit", "HEAD") == 2
    err = capsys.readouterr().err
    assert "dirty" in err and ".gitignore" in err and no_trials(root)
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t") == 0


def cli_like_launch(root: Path, hang: Any = None) -> Any:
    """A `_launch` stub that writes run.json (commit, dirty) the way fuzzer.cli does, plus metrics."""
    def fake(t: rc.Trial, cfg: rc.Cfg, r: Path, freeze: str | None) -> subprocess.CompletedProcess[str]:
        t.out.mkdir(parents=True)
        with rc._chdir(root):
            commit, dirty = rc._provenance()
        (t.out / "run.json").write_text(json.dumps({"commit": commit, "dirty": dirty}))
        (t.out / "metrics.csv").write_text(METRICS_HEADER + "\n" + metrics_row(
            hangs=hang(t) if hang else 0))
        return subprocess.CompletedProcess([], 0, "", "")
    return fake


def test_pilot_run_json_dirty_true_on_dirty_tree(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    to_git(root)
    (root / ".gitignore").write_text("targets/bin\nresults/\n# dirty\n")
    monkeypatch.setattr(rc, "_launch", cli_like_launch(root))
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t") == 0
    runs = sorted((root / "results/pilot/first_pilot").glob("toy_parser/*/s*/run.json"))
    assert len(runs) == 6
    assert all(json.loads(p.read_text())["dirty"] is True for p in runs)
    meta = json.loads((root / "results/pilot/first_pilot/campaign.json").read_text())
    assert meta["dirty"] is True


def test_freeze_commit_checks(root: Path, capsys: pytest.CaptureFixture[str],
                              planned: list[rc.Trial], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    to_git(root)
    c1 = git(root, "rev-parse", "HEAD")
    args = ["--allow-fewer-targets", "t", "--freeze-commit"]
    assert go(root, *args, "deadbeef") == 2 and no_trials(root)
    git(root, "checkout", "-qb", "side")
    (root / "x").write_text("x")
    git(root, "add", "x")
    git(root, "commit", "-qm", "side")
    side = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "-q", "main")
    assert go(root, *args, side) == 2 and no_trials(root)
    (root / "targets/triggers.json").write_text("{}")  # after the freeze: under targets/
    git(root, "add", "-A")
    git(root, "commit", "-qm", "touch targets")
    assert go(root, *args, c1) == 2 and "changed since freeze" in capsys.readouterr().err
    assert no_trials(root)
    freeze = git(root, "rev-parse", "HEAD")
    (root / "notes.txt").write_text("n")  # outside targets/ and main.yaml
    git(root, "add", "-A")
    git(root, "commit", "-qm", "docs")
    assert go(root, *args, freeze[:10]) == 0


def test_one_commit_per_campaign_aborts_on_change(root: Path, monkeypatch: pytest.MonkeyPatch,
                                                  capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    cfg = cfg_text(trials_per_config=10, concurrency=1)
    (root / "experiments/configs/main.yaml").write_text(cfg)
    to_git(root)
    launched: list[str] = []

    def fake(t: rc.Trial, cfg: rc.Cfg, r: Path, freeze: str | None) -> subprocess.CompletedProcess[str]:
        launched.append(str(t.out))
        t.out.mkdir(parents=True)
        (t.out / "run.json").write_text(json.dumps({"commit": "0" * 40, "dirty": False}))
        return subprocess.CompletedProcess([], 0, "", "")
    monkeypatch.setattr(rc, "_launch", fake)
    assert go(root, "--allow-fewer-targets", "t", "--freeze-commit", "HEAD") == 1
    assert len(launched) == 1  # no further trial after the first mismatch
    err = capsys.readouterr().err
    assert launched[0] in err
    meta = json.loads((root / "results/main/campaign.json").read_text())
    assert meta["aborted"][0]["trial"] == launched[0]


# ---- real trials -----------------------------------------------------------------------------

@needs_bin
def test_real_pilot_records_everything(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    to_git(root)
    (root / "targets/seeds/toy_parser/.DS_Store").write_bytes(b"junk")  # hidden: ignored
    monkeypatch.setattr(rc, "_cmd", lambda a: subprocess.CompletedProcess(
        a, 0, {"hw.model": "ModelX\n", "-productVersion": "99.1\n", "--version": "clang 99\nmore\n",
               }.get(a[-1], "8\n"), ""))
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "single target") == 0
    run_dir = root / "results/pilot/first_pilot"
    meta = json.loads((run_dir / "campaign.json").read_text())
    assert meta["machine"] == {"model": "ModelX", "macos_version": "99.1",
                               "clang_version": "clang 99", "hw_physicalcpu": 8}
    assert (meta["timeout_s"], meta["concurrency"], meta["hw_physicalcpu"]) == (2.5, 3, 8)
    assert meta["commit"] == git(root, "rev-parse", "HEAD")
    runs = sorted(run_dir.glob("toy_parser/*/s*/run.json"))
    assert len(runs) == 6
    seeds = set()
    for p in runs:
        j = json.loads(p.read_text())
        assert j["config"]["timeout_s"] == 2.5
        assert [f["name"] for f in j["seed_files"]] == ["S0"]
        assert j["seed_files"] == meta["seed_corpus"]["toy_parser"]["files"]
        seeds.add((j["config"]["schedule"], j["config"]["seed"]))
        assert (p.parent / "metrics.csv").exists()
    assert seeds == {(s, 7 + 1000 + i) for s in ("uniform", "fast") for i in range(3)}
    dec = json.loads((run_dir.parent / "granularity_decision.json").read_text())
    assert dec["granularity"] in ("presence_only", "hit_count_buckets")
    assert "toy_parser" in dec["targets"]
    assert git(root, "status", "--porcelain", "--untracked-files=no") == ""  # AC (d)


@needs_bin
def test_real_main_full_freeze_hash_and_clean(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = cfg_text(trials_per_config=10, seconds_per_trial=0.2, schedules=["uniform"])
    (root / "experiments/configs/main.yaml").write_text(cfg)
    to_git(root)
    head8 = git(root, "rev-parse", "HEAD")[:8]
    assert go(root, "--allow-fewer-targets", "t", "--freeze-commit", head8) == 0
    runs = list((root / "results/main").glob("toy_parser/uniform/s*/run.json"))
    assert len(runs) == 10
    js = [json.loads(p.read_text()) for p in runs]
    assert all(j["freeze_commit"] == git(root, "rev-parse", "HEAD") and j["dirty"] is False
               for j in js)
    assert {j["config"]["seed"] for j in js} == set(range(7, 17))


def test_granularity_decision_rule(tmp_path: Path) -> None:
    def trial(name: str, paths: int, corpus: int) -> tuple[str, Path]:
        d = tmp_path / name
        d.mkdir()
        (d / "metrics.csv").write_text(
            "elapsed_s,execs,edges,corpus_size,distinct_path_ids,crash_events,crashes_saved,"
            f"hangs,hang_time_s\n1,1,1,{corpus},{paths},0,0,0,0\n")
        return name.split("_")[0], d
    d = rc.granularity_decision([trial("a_1", 30, 10), trial("a_2", 30, 10),
                                 trial("b_1", 30, 20), trial("b_2", 30, 20)])
    assert d["targets"]["a"]["trigger"] is False and d["targets"]["b"]["trigger"] is True  # 30 < 40
    assert d["granularity"] == "hit_count_buckets"
    assert rc.granularity_decision([trial("c_1", 19, 5)])["targets"]["c"]["trigger"] is True


# ---- probe layout ----------------------------------------------------------------------------

def _shape(pairs: int, c: int) -> list[tuple[int, int]]:
    ps = [(f"t{k // 2}", "uniform" if k % 2 == 0 else "fast") for k in range(pairs)]
    return [(len(w), sum(1 for x in w if x[3])) for w in rc.probe_layout(ps, c)]


@pytest.mark.parametrize("pairs,c,want", [
    (6, 1, [(1, 1)] * 6), (6, 3, [(3, 3), (3, 3)]), (6, 4, [(4, 4), (4, 2)]),
    (6, 5, [(5, 5), (5, 1)]), (6, 6, [(6, 6)]), (6, 10, [(10, 6)]),
    (4, 1, [(1, 1)] * 4), (4, 3, [(3, 3), (3, 1)]), (4, 5, [(5, 4)])])
def test_probe_wave_layout(pairs: int, c: int, want: list[tuple[int, int]]) -> None:
    assert _shape(pairs, c) == want


def test_probe_seeds_fillers_continue_cycle(root: Path) -> None:
    cfg = rc.Cfg(2, 1, 7, ("targets/bin/toy_parser",), ("uniform", "fast"), 1.0, 5)
    ts = rc.plan("probe", cfg, ["toy_parser"], root / "r")
    counted = [t for t in ts if t.counted]
    assert {(t.schedule, t.seed) for t in counted} == {("uniform", 2007), ("fast", 2007)}
    assert len(ts) == 5 and len({(t.schedule, t.seed) for t in ts}) == 5  # no shared seed
    assert [t.counted for t in ts] == [True, True, False, False, False]


# ---- crash probe (executor stubbed) ----------------------------------------------------------

class CrashFake:
    inits = 0
    closes = 0
    slow_bug: str | None = None  # data (hex) of the bug that times out

    def __init__(self, t: Path, timeout_s: float) -> None:
        CrashFake.inits += 1

    def run(self, data: bytes) -> ExecResult:
        t = {"42554761": 0.30, "21616161": 0.10}[data.hex()]
        if data.hex() == CrashFake.slow_bug:
            return ExecResult(None, None, True, frozenset(), 5.0, b"")
        return ExecResult(None, 6, False, frozenset(), t, data)

    def close(self) -> None:
        CrashFake.closes += 1


@pytest.fixture
def crash_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    CrashFake.inits = CrashFake.closes = 0
    CrashFake.slow_bug = None
    monkeypatch.setattr(rc, "Executor", CrashFake)
    monkeypatch.setattr(rc, "crash_site", lambda err, src: (
        "check" if err.hex() == TOY_TRIGGERS["toy-1"] else "scan"))


def test_crash_probe_outputs(root: Path, crash_stub: None) -> None:
    (root / "experiments/configs/main.yaml").write_text(cfg_text(concurrency=2))
    to_git(root)
    commit = git(root, "rev-parse", "HEAD")
    assert go(root, "--crash-probe", "--rounds", "3", "--allow-fewer-targets", "t") == 0
    out = root / "results/probe" / commit
    with (out / "crash_durations.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == rc.CRASH_COLUMNS
    for bug in ("toy-1", "toy-2"):
        assert sum(r["bug_id"] == bug for r in rows) == 2 * 3  # c x R
    j = json.loads((out / "crash_durations.json").read_text())
    assert j["D_max"] == 0.30 and j["D_max_bug"] == "toy-1" and j["R"] == 3
    assert j["bugs"]["toy-2"]["max_wall_s"] == 0.10 and j["concurrency"] == 2
    assert set(j) >= {"commit", "probe_timeout_s", "hw_physicalcpu"}
    assert j["commit"] == commit and j["dirty"] is False
    assert not [p for p in (root / "results").rglob("run.json")]
    assert CrashFake.inits == CrashFake.closes > 0


def test_crash_probe_timeout_invalidates(root: Path, crash_stub: None,
                                         capsys: pytest.CaptureFixture[str]) -> None:
    to_git(root)
    CrashFake.slow_bug = TOY_TRIGGERS["toy-2"]
    assert go(root, "--crash-probe", "--allow-fewer-targets", "t") == 2
    err = capsys.readouterr().err
    assert "toy-2" in err
    out = root / "results/probe" / git(root, "rev-parse", "HEAD")
    assert "D_max" not in (out / "crash_durations.csv").read_text()
    assert not (out / "crash_durations.json").exists()
    assert not list((root / "results").rglob("run.json"))
    assert CrashFake.inits == CrashFake.closes


def test_timeout_floor(root: Path, crash_stub: None, capsys: pytest.CaptureFixture[str]) -> None:
    to_git(root)
    rc.check_floor(3.0, 10, [0.3, 0.1])  # equal passes
    with pytest.raises(rc.Refusal):
        rc.check_floor(2.9, 10, [0.3])
    with pytest.raises(rc.Refusal):
        rc.check_floor(5.0, 1, [0.3])
    # timeout_s 2.5 < 10 x 0.30: the floor refuses (k = 8 gives 2.4 and passes)
    assert go(root, "--crash-probe", "--allow-fewer-targets", "t", "--k", "10") == 2
    assert "k x D_max" in capsys.readouterr().err
    second = str(root / "results/second")  # the first call's output dir is now non-empty
    assert go(root, "--crash-probe", "--allow-fewer-targets", "t", "--k", "8",
              "--out", second) == 0


# ---- partial streams survive an external kill (AC "Partial streams survive...") --------------

@needs_bin
def test_streams_survive_sigkill(tmp_path: Path) -> None:
    out = tmp_path / "t"
    code = textwrap.dedent(f"""
        from pathlib import Path
        from fuzzer import fuzzer
        fuzzer.run(fuzzer.FuzzConfig(Path({str(REPO / 'targets/bin/toy_parser')!r}), "uniform", 60,
            1, Path({str(out)!r}), Path({str(REPO / 'targets/seeds/toy_parser')!r})))
    """)
    p = subprocess.Popen([sys.executable, "-c", code], env={**os.environ, "PYTHONPATH": str(REPO / "src")})
    try:
        deadline = time.monotonic() + 10
        m = out / "metrics.csv"
        while time.monotonic() < deadline:
            if m.exists() and len(m.read_text().splitlines()) >= 2:
                break
            time.sleep(0.05)
        else:
            pytest.fail("no data row on disk before the deadline")
    finally:
        p.send_signal(signal.SIGKILL)
        p.wait()
    for name in ("metrics.csv", "crash_events.csv"):
        rows = list(csv.reader((out / name).open(newline="")))
        assert rows[0] and all(len(r) == len(rows[0]) for r in rows[1:])
        if name == "metrics.csv":
            assert rows[0][0] == "elapsed_s" and len(rows) >= 2


# ---- load_yaml / _num refusals (B2) ----------------------------------------------------------

def _refused(root: Path, cfg: str, capsys: pytest.CaptureFixture[str]) -> str:
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t", cfg=cfg) == 2
    assert no_trials(root)
    return capsys.readouterr().err


def test_duplicate_key_refused_naming_line(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = cfg_text()
    err = _refused(root, base + "concurrency: 2\n", capsys)
    assert "duplicate key 'concurrency'" in err and f":{len(base.splitlines()) + 1}:" in err


def test_tab_indentation_refused_naming_line(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = cfg_text().replace("  - targets/bin/toy_parser", "\t- targets/bin/toy_parser")
    n = next(i for i, ln in enumerate(cfg.splitlines(), 1) if ln.startswith("\t"))
    err = _refused(root, cfg, capsys)
    assert "tab" in err and f":{n}:" in err


@pytest.mark.parametrize("key,val", [("timeout_s", "nan"), ("timeout_s", "inf"),
                                     ("seconds_per_trial", "-inf"),
                                     ("seconds_per_trial", "nan")])
def test_nonfinite_number_refused(root: Path, key: str, val: str,
                                  capsys: pytest.CaptureFixture[str]) -> None:
    err = _refused(root, cfg_text(**{key: val}), capsys)
    assert repr(key) in err and val in err


# ---- probe path through run() (B3) -----------------------------------------------------------

def _probe_summary_file(root: Path) -> dict[str, Any]:
    (path,) = (root / "results/probe").glob("*/probe/probe_summary.json")
    return json.loads(path.read_text())  # type: ignore[no-any-return]


def test_probe_hang_only_in_filler_violates_rule(root: Path, clean_unknown: None, monkeypatch: pytest.MonkeyPatch,
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    monkeypatch.setattr(rc, "_launch", stub_launch(
        lambda t: {} if t.counted else {"hangs": 2, "hang_time": 5.6}))
    assert go(root, "--kind", "probe", "--allow-fewer-targets", "t") == 1
    assert "Hang rule" in capsys.readouterr().err
    summ = _probe_summary_file(root)
    assert summ["hang_rule_violated"] is True
    rows = summ["rows"]
    assert [r["role"] for r in rows if r["hangs"]] == ["filler, not used"]
    assert sum(r["role"] == "counted" for r in rows) == 2 and len(rows) == 3


def test_probe_no_hangs_exits_zero(root: Path, clean_unknown: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    monkeypatch.setattr(rc, "_launch", stub_launch(lambda t: {}))
    assert go(root, "--kind", "probe", "--allow-fewer-targets", "t") == 0
    summ = _probe_summary_file(root)
    assert summ["hang_rule_violated"] is False and len(summ["rows"]) == 3


def test_probe_summary_columns_from_known_values(root: Path, clean_unknown: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])

    def spec(t: rc.Trial) -> dict[str, Any]:
        if t.schedule == "uniform" and t.counted:  # timeout_s is 2.5: 5.6 - 2 x 2.5 = 0.6
            return {"execs": 1000, "elapsed": 10.0, "hangs": 2, "hang_time": 5.6}
        return {"execs": 500, "elapsed": 4.0}
    monkeypatch.setattr(rc, "_launch", stub_launch(spec))
    assert go(root, "--kind", "probe", "--allow-fewer-targets", "t") == 1  # a counted hang
    by = {(r["schedule"], r["role"]): r for r in _probe_summary_file(root)["rows"]}
    u = by[("uniform", "counted")]
    assert u["exec_per_s"] == pytest.approx(100.0) and u["hang_rate"] == pytest.approx(0.002)
    assert u["hang_overhead_s"] == pytest.approx(0.6)
    assert u["hang_overhead_per_hang_s"] == pytest.approx(0.3)
    f = by[("fast", "counted")]
    assert f["exec_per_s"] == pytest.approx(125.0) and f["hang_overhead_s"] == 0.0
    assert f["hang_overhead_per_hang_s"] is None


def test_probe_summary_direct(tmp_path: Path) -> None:
    def trial(name: str, counted: bool, body: str | None) -> rc.Trial:
        d = tmp_path / name
        d.mkdir()
        if body is not None:
            (d / "metrics.csv").write_text(METRICS_HEADER + "\n" + body + "\n")
        return rc.Trial("toy_parser", "fast", 1, d, 1, counted)
    ts = [trial("a", True, metrics_row(execs=300, elapsed=3.0)),
          trial("b", False, metrics_row(execs=0, elapsed=0.0, hangs=1, hang_time=1.5)),
          trial("gone", True, None)]  # no metrics.csv: skipped
    summ = rc.probe_summary(ts, timeout_s=1.0)
    assert [r["role"] for r in summ["rows"]] == ["counted", "filler, not used"]
    a, b = summ["rows"]
    assert a["exec_per_s"] == pytest.approx(100.0) and a["hang_overhead_per_hang_s"] is None
    assert b["exec_per_s"] == 0.0 and b["hang_rate"] == 0.0
    assert b["hang_overhead_s"] == pytest.approx(0.5) and b["hang_overhead_per_hang_s"] == pytest.approx(0.5)
    assert summ["hang_rule_violated"] is True
    assert rc.probe_summary(ts[:1], 1.0)["hang_rule_violated"] is False


# ---- granularity decision file (B5) ----------------------------------------------------------

def test_completed_pilot_writes_decision(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    monkeypatch.setattr(rc, "_launch", stub_launch(lambda t: {}))
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t") == 0
    dec = json.loads((root / "results/pilot/granularity_decision.json").read_text())
    assert "toy_parser" in dec["targets"]


@pytest.mark.parametrize("kind,name", [("first_pilot", "granularity_decision.json"),
                                       ("restarted_first_pilot", "granularity_decision_restarted.json")])
def test_existing_decision_refused_never_overwritten(root: Path, kind: str, name: str,
                                                     monkeypatch: pytest.MonkeyPatch,
                                                     capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    launched: list[rc.Trial] = []
    monkeypatch.setattr(rc, "_launch", lambda t, *a: launched.append(t))  # type: ignore[arg-type,func-returns-value]
    dec = root / "results/pilot" / name
    dec.parent.mkdir(parents=True)
    dec.write_bytes(b"first decision")
    assert go(root, "--kind", kind, "--allow-fewer-targets", "t") == 2
    assert name in capsys.readouterr().err
    assert dec.read_bytes() == b"first decision" and not launched
    assert not (root / "results/pilot" / kind).exists()


def test_aborted_pilot_writes_no_decision(root: Path, monkeypatch: pytest.MonkeyPatch,
                                          capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    seen: list[rc.Trial] = []

    def fake(t: rc.Trial, *a: Any) -> subprocess.CompletedProcess[str]:
        seen.append(t)
        return subprocess.CompletedProcess([], 1, "", "boom")
    monkeypatch.setattr(rc, "_launch", fake)
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t",
              cfg=cfg_text(concurrency=1)) == 1
    err = capsys.readouterr().err
    assert "granularity_decision.json not written" in err and str(seen[0].out) in err
    assert not (root / "results/pilot/granularity_decision.json").exists()


def test_pilot_trial_without_final_row_writes_no_decision(
        root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    monkeypatch.setattr(rc, "_launch", stub_launch(
        lambda t: None if (t.schedule, t.seed) == ("fast", 1007) else {}))  # header-only csv
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t") == 1
    err = capsys.readouterr().err
    assert "trials without a final row" in err and "fast/s1007" in err and "uniform/s1007" not in err
    assert not (root / "results/pilot/granularity_decision.json").exists()


def test_aborted_pilot_with_all_final_rows_writes_no_decision(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Abort on the 6th trial while every trial has a final row: still no decision."""
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    n = {"k": 0}
    inner = stub_launch(lambda t: {})

    def fake(t: rc.Trial, *a: Any) -> subprocess.CompletedProcess[str]:
        inner(t, *a)
        n["k"] += 1
        return subprocess.CompletedProcess([], 1 if n["k"] == 6 else 0, "", "late failure")
    monkeypatch.setattr(rc, "_launch", fake)
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t",
              cfg=cfg_text(concurrency=1)) == 1
    assert n["k"] == 6
    assert not (root / "results/pilot/granularity_decision.json").exists()


def test_final_row_half_written_last_row_is_none(tmp_path: Path) -> None:
    (tmp_path / "metrics.csv").write_text(METRICS_HEADER + "\n" + metrics_row() + "\n10.5,12")
    assert rc.final_row(tmp_path) is None


# ---- main config and trial count (B6, N5), targets path (N4), dmax-json (N6), env (N7) -------

def test_main_refuses_other_config(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    other = root / "experiments/configs/other.yaml"
    other.write_text(cfg_text())
    assert rc.run(["experiments/configs/other.yaml", "--allow-fewer-targets", "t",
                   "--freeze-commit", "HEAD"], root=root) == 2
    assert "main.yaml" in capsys.readouterr().err and no_trials(root)


def test_pilot_accepts_other_config(root: Path, planned: list[rc.Trial],
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    (root / "experiments/configs/other.yaml").write_text(cfg_text())
    assert rc.run(["experiments/configs/other.yaml", "--kind", "first_pilot",
                   "--allow-fewer-targets", "t"], root=root) == 0


def test_main_refuses_fewer_than_ten_trials(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert go(root, "--allow-fewer-targets", "t", "--freeze-commit", "HEAD",
              cfg=cfg_text(trials_per_config=9)) == 2
    err = capsys.readouterr().err
    assert "trials_per_config >= 10" in err and "got 9" in err and no_trials(root)


def test_target_path_must_match_launch_path(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (root / "elsewhere").mkdir()
    shutil.copy(REPO / "targets/bin/toy_parser", root / "elsewhere/toy_parser")
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t",
              cfg=cfg_text(targets=["elsewhere/toy_parser"])) == 2
    err = capsys.readouterr().err
    assert "trials launch" in err and "targets/bin/toy_parser" in err and no_trials(root)


@pytest.mark.parametrize("content", [None, "not json", "{}", '{"D_max": "x"}'])
def test_dmax_json_bad_file_clear_refusal(root: Path, content: str | None,
                                          capsys: pytest.CaptureFixture[str]) -> None:
    f = root / "d.json"
    if content is not None:
        f.write_text(content)
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t", "--k", "2",
              "--dmax-json", str(f)) == 2
    err = capsys.readouterr().err
    assert "--dmax-json" in err and "Traceback" not in err and no_trials(root)


def test_crash_probe_refuses_unknown_commit(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert go(root, "--crash-probe", "--allow-fewer-targets", "t") == 2  # no git repo here
    assert "unknown" in capsys.readouterr().err and no_trials(root)


@pytest.mark.parametrize("old,want", [("", "SRC"), ("/x", "SRC:/x")])
def test_launch_pythonpath_has_no_empty_entry(root: Path, old: str, want: str,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class FakePopen:
        returncode = 0
        pid = 0

        def __init__(self, argv: list[str], **kw: Any) -> None:
            seen.update(kw)

        def communicate(self) -> tuple[str, str]:
            return "", ""
    monkeypatch.setattr(rc.subprocess, "Popen", FakePopen)
    monkeypatch.setenv("PYTHONPATH", old)
    cfg = rc.Cfg(10, 1, 7, ("targets/bin/toy_parser",), ("uniform",), 1.0, 1)
    rc._launch(rc.Trial("toy_parser", "uniform", 7, root / "o"), cfg, root, None)
    assert seen["env"]["PYTHONPATH"] == want.replace("SRC", str(rc.SRC))


# ---- baseline, abort handling, smoke (lead decisions, 2026-11-15) -----------------------------

STUB_TRIAL = textwrap.dedent("""
    HEADER = "@HEADER@"
    import os, signal, sys, time
    a = sys.argv
    seed, out = int(a[a.index("--seed") + 1]), a[a.index("--out") + 1]
    os.makedirs(out)
    open(os.path.join(out, "pid"), "w").write(str(os.getpid()))
    open(os.path.join(out, "argv"), "w").write(" ".join(a))
    open(os.path.join(out, "metrics.csv"), "w").write(HEADER + "\\n1,1,1,1,1,0,0,0,0\\n")
    mode = os.environ.get("STUB_MODE", "")
    if "fail" in mode and seed == 1007 and "uniform" in a:
        time.sleep(1.0)
        sys.exit(1)
    if "ignore" in mode and "fast" in a:
        def on_term(*_: object) -> None:  # record when SIGTERM arrived, then keep running
            open(os.path.join(out, "term"), "w").write(repr(time.time()))
        signal.signal(signal.SIGTERM, on_term)
    if "hang" in mode:
        time.sleep(60)
""")


@pytest.fixture
def stub_trials(tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Real `_launch` (Popen), but the child is STUB_TRIAL instead of fuzzer.cli."""
    script = tmp_path / "stub_trial.py"
    script.write_text(STUB_TRIAL.replace("@HEADER@", METRICS_HEADER))
    real = subprocess.Popen

    def popen(argv: list[str], **kw: Any) -> Any:
        return real([sys.executable, str(script), *argv[3:]], **kw)
    monkeypatch.setattr(rc.subprocess, "Popen", popen)
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    monkeypatch.setattr(rc, "ABORT_GRACE_S", 1.0)


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def check_term_then_kill(d: Path) -> None:
    """A SIGTERM-handling stub saw SIGTERM first, and lived on for (about) the whole grace."""
    marks = [float(m.read_text()) for m in d.glob("*/*/s*/term")]
    assert marks  # SIGTERM arrived before any SIGKILL
    assert all(time.time() - m >= 0.8 * rc.ABORT_GRACE_S for m in marks)  # killed only after grace


def meta_of(d: Path) -> dict[str, Any]:
    out: dict[str, Any] = json.loads((d / "campaign.json").read_text())
    return out


def test_abort_terminates_then_kills_running_and_marks_all(
        root: Path, stub_trials: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUB_MODE", "fail,ignore,hang")  # fast ignores SIGTERM
    t0 = time.monotonic()
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t") == 1  # c = 3
    assert time.monotonic() - t0 < 20
    d = root / "results/pilot/first_pilot"
    trials = meta_of(d)["trials"]
    assert len(trials) == 6
    bad = [r for r in trials.values() if "error" in r]
    assert len(bad) == 1 and bad[0]["seed"] == 1007 and bad[0]["schedule"] == "uniform"
    others = [r for r in trials.values() if "error" not in r]
    assert all(r["aborted"] for r in others)
    assert sum(1 for r in others if r.get("started") is False) == 3  # never launched
    pids = [int((p / "pid").read_text()) for p in d.glob("*/*/s*") if (p / "pid").exists()]
    assert len(pids) == 3 and not any(alive(x) for x in pids)  # incl. the SIGTERM-ignorer
    check_term_then_kill(d)
    assert not (root / "results/pilot/granularity_decision.json").exists()


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_runner_signal_aborts_all_trials(root: Path, stub_trials: None,
                                         monkeypatch: pytest.MonkeyPatch, sig: int) -> None:
    import threading
    monkeypatch.setenv("STUB_MODE", "ignore,hang")  # fast trials handle SIGTERM and live on
    before = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    threading.Timer(2.0, os.kill, (os.getpid(), sig)).start()
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t") == 1
    assert {s: signal.getsignal(s) for s in before} == before  # handlers restored
    d = root / "results/pilot/first_pilot"
    m = meta_of(d)
    assert len(m["trials"]) == 6 and all(r["aborted"] for r in m["trials"].values())
    assert any("signal" in e["error"] for e in m["aborted"]) and "finished_at" in m
    pids = [int(p.read_text()) for p in d.glob("*/*/s*/pid")]
    assert len(pids) == 3 and not any(alive(x) for x in pids)
    check_term_then_kill(d)
    assert all(len((p / "metrics.csv").read_text().splitlines()) == 2
               for p in d.glob("*/*/s*") if (p / "pid").exists())  # partial files survive


def test_baseline_probe_runs_at_c1_whatever_yaml_says(root: Path, clean_unknown: None,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    monkeypatch.setattr(rc, "_launch", stub_launch(lambda t: {}))
    assert go(root, "--kind", "probe", "--baseline", "--allow-fewer-targets", "t",
              cfg=cfg_text(concurrency=5, targets=["targets/bin/toy_parser",
                                                   "targets/bin/tlv_parser",
                                                   "targets/bin/mini_format"])) == 0
    d = root / "results/probe/unknown/baseline"
    m = meta_of(d)
    assert m["concurrency"] == 1 and m["config"]["concurrency"] == 1 and m["baseline"] is True
    assert "baseline: informs (d) and c, not used" in m["label"]
    ts = list(m["trials"].values())
    assert len(ts) == 6 and all(r["counted"] for r in ts)  # no fillers
    assert sorted(r["wave"] for r in ts) == list(range(6))  # six waves of 1
    assert {r["seed"] for r in ts} == {7 + 2000}
    assert json.loads((d / "probe_summary.json").read_text())["baseline"] is True


def test_baseline_executes_one_at_a_time(root: Path, clean_unknown: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    live = {"now": 0, "max": 0}
    inner = stub_launch(lambda t: {})

    def fake(t: rc.Trial, *a: Any) -> subprocess.CompletedProcess[str]:
        live["now"] += 1
        live["max"] = max(live["max"], live["now"])
        time.sleep(0.05)
        live["now"] -= 1
        return inner(t, *a)
    monkeypatch.setattr(rc, "_launch", fake)
    assert go(root, "--kind", "probe", "--baseline", "--allow-fewer-targets", "t") == 0
    assert live["max"] == 1


def test_baseline_refusals(root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
                           monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    assert go(root, "--baseline", "--allow-fewer-targets", "t") == 2  # kind main
    assert go(root, "--kind", "first_pilot", "--baseline", "--allow-fewer-targets", "t") == 2
    assert go(root, "--kind", "probe", "--baseline", "--k", "2", "--allow-fewer-targets", "t") == 2
    f = tmp_path / "d.json"
    f.write_text(json.dumps({"D_max": 0.1, "baseline": True}))
    assert go(root, "--k", "2", "--dmax-json", str(f), "--allow-fewer-targets", "t") == 2
    assert "baseline" in capsys.readouterr().err and no_trials(root)


def test_baseline_dmax_json_alone_refused(root: Path, tmp_path: Path,
                                          capsys: pytest.CaptureFixture[str],
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    f = tmp_path / "d.json"
    f.write_text(json.dumps({"D_max": 0.1}))
    assert go(root, "--kind", "probe", "--baseline", "--dmax-json", str(f),
              "--allow-fewer-targets", "t") == 2
    assert "baseline" in capsys.readouterr().err and no_trials(root)


@pytest.mark.parametrize("baseline", [False, True])
def test_crash_measurement_refuses_existing_output(root: Path, crash_stub: None, tmp_path: Path,
                                                 capsys: pytest.CaptureFixture[str],
                                                 baseline: bool) -> None:
    to_git(root)
    out = tmp_path / "official"
    out.mkdir()
    (out / "crash_durations.json").write_text("{}")
    args = ["--crash-probe", "--rounds", "2", "--allow-fewer-targets", "t", "--out", str(out)]
    assert go(root, *args, *(["--baseline"] if baseline else [])) == 2
    assert "already exists" in capsys.readouterr().err
    assert [p.name for p in out.iterdir()] == ["crash_durations.json"]
    assert (out / "crash_durations.json").read_text() == "{}"


def test_baseline_then_official_crash_measurement_sequence(
        root: Path, crash_stub: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Nov 16 order: baseline probe, baseline crash, then the official crash on its default dir."""
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    to_git(root)
    commit = git(root, "rev-parse", "HEAD")
    monkeypatch.setattr(rc, "_launch", stub_launch(lambda t: {}))
    assert go(root, "--kind", "probe", "--baseline", "--allow-fewer-targets", "t") == 0
    assert go(root, "--crash-probe", "--baseline", "--rounds", "2", "--allow-fewer-targets",
              "t") == 0
    base = root / "results/probe" / commit
    assert (base / "baseline").is_dir() and (base / "baseline_crash").is_dir()
    assert go(root, "--crash-probe", "--rounds", "2", "--allow-fewer-targets", "t") == 0
    assert (base / "crash_durations.json").exists()
    assert go(root, "--crash-probe", "--rounds", "2", "--allow-fewer-targets", "t") == 2  # once


def test_baseline_crash_probe_c1_own_dir_no_floor(root: Path, crash_stub: None) -> None:
    (root / "experiments/configs/main.yaml").write_text(cfg_text(concurrency=4))
    to_git(root)
    commit = git(root, "rev-parse", "HEAD")
    assert go(root, "--crash-probe", "--baseline", "--rounds", "2", "--allow-fewer-targets",
              "t") == 0
    out = root / "results/probe" / commit / "baseline_crash"
    j = json.loads((out / "crash_durations.json").read_text())
    assert j["concurrency"] == 1 and j["baseline"] is True and j["D_max"] == 0.30
    assert j["label"] == rc.BASELINE_LABEL
    with (out / "crash_durations.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert {r["concurrency"] for r in rows} == {"1"} and len(rows) == 2 * 2  # bugs x R in total
    assert not (root / "results/probe" / commit / "crash_durations.json").exists()


def test_smoke_plan_seeds_and_sets(root: Path) -> None:
    cfg = rc.Cfg(10, 1, 7, ("a", "b", "c"), ("uniform", "fast"), 1.0, 5)
    ts = rc.plan("smoke", cfg, ["a", "b", "c"], root / "r")
    assert len(ts) == 6 and {t.seed for t in ts} == {7 + 9000}
    assert all(t.max_execs == 200 for t in ts)
    assert rc.seed_sets(cfg, ["a", "b", "c"])["smoke"] == {7 + 9000}
    assert "smoke" in rc.SEED_OFFSETS
    rc.check_disjoint(cfg, ["a", "b", "c"])
    rc.check_disjoint(rc.Cfg(10, 1, 0, ("a",), ("uniform",), 1.0, 5), ["a"])


def test_smoke_overlap_would_be_caught(root: Path, monkeypatch: pytest.MonkeyPatch,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setitem(rc.SEED_OFFSETS, "smoke", 1000)  # collides with first_pilot
    assert go(root, "--allow-fewer-targets", "t") == 2
    assert "smoke" in capsys.readouterr().err and no_trials(root)


def test_smoke_run_dirty_tree_metadata_and_launch(root: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    seen: list[rc.Trial] = []
    inner = stub_launch(lambda t: {})

    def fake(t: rc.Trial, *a: Any) -> subprocess.CompletedProcess[str]:
        seen.append(t)
        return inner(t, *a)
    monkeypatch.setattr(rc, "_launch", fake)
    to_git(root)
    (root / ".gitignore").write_text("targets/bin\nresults/\n# dirty\n")
    assert go(root, "--kind", "smoke", "--allow-fewer-targets", "t") == 0
    d = root / "results/smoke/smoke"
    m = meta_of(d)
    assert m["kind"] == "smoke" and m["excluded_from_analysis"] is True and m["dirty"] is True
    assert len(seen) == 2 and {t.seed for t in seen} == {7 + 9000}  # one toy trial per schedule
    assert not list((root / "results").rglob("granularity_decision*"))
    assert not (d / "probe_summary.json").exists()


def test_launch_passes_max_execs(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class FakePopen:
        returncode = 0
        pid = 0

        def __init__(self, argv: list[str], **kw: Any) -> None:
            seen["argv"] = argv

        def communicate(self) -> tuple[str, str]:
            return "", ""
    monkeypatch.setattr(rc.subprocess, "Popen", FakePopen)
    cfg = rc.Cfg(10, 1, 7, ("targets/bin/toy_parser",), ("uniform",), 1.0, 1)
    rc._launch(rc.Trial("toy_parser", "uniform", 7, root / "o", max_execs=200), cfg, root, None)
    assert seen["argv"][seen["argv"].index("--max-execs") + 1] == "200"
    rc._launch(rc.Trial("toy_parser", "uniform", 7, root / "o"), cfg, root, None)
    assert "--max-execs" not in seen["argv"]


def test_runner_exception_aborts_all_trials(root: Path, stub_trials: None,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUB_MODE", "ignore,hang")
    real = rc._launch

    def boom(t: rc.Trial, *a: Any) -> Any:
        if (t.schedule, t.seed) == ("uniform", 1008):  # the third launch, others are running
            time.sleep(1.5)
            raise RuntimeError("runner bug")
        return real(t, *a)
    monkeypatch.setattr(rc, "_launch", boom)
    with pytest.raises(RuntimeError, match="runner bug"):
        go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t")
    d = root / "results/pilot/first_pilot"
    m = meta_of(d)
    assert len(m["trials"]) == 6 and all(r["aborted"] for r in m["trials"].values())
    assert any("RuntimeError" in e["error"] for e in m["aborted"])
    pids = [int(p.read_text()) for p in d.glob("*/*/s*/pid")]
    assert len(pids) == 2 and not any(alive(x) for x in pids)
    check_term_then_kill(d)
    assert all(len((p / "metrics.csv").read_text().splitlines()) == 2
               for p in d.glob("*/*/s*") if (p / "pid").exists())  # partial files kept


def test_runner_exception_in_probe_wave_marks_later_waves_not_started(
        root: Path, clean_unknown: None, stub_trials: None, monkeypatch: pytest.MonkeyPatch) -> None:
    import threading
    monkeypatch.setenv("STUB_MODE", "hang")
    real = rc._launch
    lock, n = threading.Lock(), [0]

    def boom(t: rc.Trial, *a: Any) -> Any:
        with lock:
            n[0] += 1
            last = n[0] == 5  # the fifth launch of wave 0, the other four are running
        if last:
            time.sleep(1.0)
            raise RuntimeError("runner bug")
        return real(t, *a)
    monkeypatch.setattr(rc, "_launch", boom)
    cfg = cfg_text(concurrency=5, targets=["targets/bin/toy_parser", "targets/bin/tlv_parser",
                                           "targets/bin/mini_format"])
    with pytest.raises(RuntimeError, match="runner bug"):
        go(root, "--kind", "probe", "--allow-fewer-targets", "t", cfg=cfg)
    ts = list(meta_of(root / "results/probe/unknown/probe")["trials"].values())
    assert len(ts) == 10 and all(r["aborted"] for r in ts)
    later = [r for r in ts if r["wave"] == 1]
    assert len(later) == 5 and all(r["started"] is False for r in later)


def test_launch_after_abort_kills_sigterm_ignorer(root: Path, stub_trials: None,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUB_MODE", "ignore,hang")
    rc._ABORT.set()
    cfg = rc.Cfg(10, 1, 7, ("targets/bin/toy_parser",), ("fast",), 1.0, 1)
    t0 = time.monotonic()
    p = rc._launch(rc.Trial("toy_parser", "fast", 1, root / "o"), cfg, root, None)
    assert p.returncode == -signal.SIGKILL and time.monotonic() - t0 < 20


def test_abort_partial_files_kept_and_nothing_starts_after(
        root: Path, stub_trials: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUB_MODE", "fail,hang")
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t") == 1
    d = root / "results/pilot/first_pilot"
    started = [p for p in d.glob("*/*/s*") if (p / "pid").exists()]
    assert len(started) == 3 and all((p / "metrics.csv").exists() for p in started)
    assert len(list(d.glob("*/*/s*"))) == 3  # the queued three never got a directory


def test_without_baseline_probe_runs_at_5_and_crash_5xR(root: Path, crash_stub: None,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    monkeypatch.setattr(rc, "_launch", stub_launch(lambda t: {}))
    cfg = cfg_text(concurrency=5, targets=["targets/bin/toy_parser", "targets/bin/tlv_parser",
                                           "targets/bin/mini_format"])
    (root / "experiments/configs/main.yaml").write_text(cfg)
    (root / "experiments/configs/toy.yaml").write_text(cfg_text(concurrency=5))
    to_git(root)
    commit = git(root, "rev-parse", "HEAD")
    assert go(root, "--kind", "probe", "--allow-fewer-targets", "t") == 0
    ts = meta_of(root / "results/probe" / commit / "probe")["trials"].values()
    assert sorted(r["wave"] for r in ts) == [0] * 5 + [1] * 5  # six pairs: two waves of 5
    assert rc.run(["experiments/configs/toy.yaml", "--crash-probe", "--rounds", "2",
                   "--allow-fewer-targets", "t"], root=root) == 0
    out = root / "results/probe" / git(root, "rev-parse", "HEAD")
    with (out / "crash_durations.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert sum(r["bug_id"] == "toy-1" for r in rows) == 5 * 2
    assert "baseline" not in json.loads((out / "crash_durations.json").read_text())


@pytest.mark.parametrize("fail", [False, True])
def test_smoke_real_argv_pass_fail(root: Path, monkeypatch: pytest.MonkeyPatch,
                                   capsys: pytest.CaptureFixture[str], fail: bool) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    argvs: list[list[str]] = []
    live = {"now": 0, "max": 0}
    lock = __import__("threading").Lock()
    five = __import__("threading").Event()  # set once five launches are live at the same time
    inner = stub_launch(lambda t: {})

    def fake(argv: list[str], **kw: Any) -> Any:
        with lock:
            argvs.append(argv)
            nth = len(argvs)
            live["now"] += 1
            live["max"] = max(live["max"], live["now"])
            if live["now"] == 5:
                five.set()
        five.wait(5.0)  # hold until five are live (or time out: then the assert below fails)
        out = Path(argv[argv.index("--out") + 1])
        t = rc.Trial("toy_parser", "uniform", 0, out)
        inner(t, None, None, None)
        with lock:
            live["now"] -= 1
        return subprocess.CompletedProcess(argv, 1 if fail and nth == 6 else 0, "", "boom")

    class P:
        def __init__(self, argv: list[str], **kw: Any) -> None:
            self.argv, self.returncode, self.pid = argv, 0, 0

        def wait(self, timeout: float | None = None) -> int:
            return 0

        def communicate(self) -> tuple[str, str]:
            r = fake(self.argv)
            self.returncode = r.returncode
            return "", "boom"
    real = subprocess.Popen

    def popen(argv: list[str], **kw: Any) -> Any:
        return P(argv) if argv[1:3] == ["-m", "fuzzer.cli"] else real(argv, **kw)
    monkeypatch.setattr(rc.subprocess, "Popen", popen)
    tlv, mini = "targets/bin/tlv_parser", "targets/bin/mini_format"
    cfg = cfg_text(concurrency=5, targets=["targets/bin/toy_parser", tlv, mini])
    assert go(root, "--kind", "smoke", "--allow-fewer-targets", "t", cfg=cfg) == (1 if fail else 0)
    assert len(argvs) == 6 and live["max"] == 5
    assert {(Path(av[av.index("--target") + 1]).name, av[av.index("--schedule") + 1])
            for av in argvs} == {(t, s) for t in ("toy_parser", "tlv_parser", "mini_format")
                                 for s in ("uniform", "fast")}
    for av in argvs:
        assert av[av.index("--max-execs") + 1] == "200" and av[av.index("--seed") + 1] == "9007"
        assert av[av.index("--timeout") + 1] == "2.5"
        assert str(root / "results/smoke") in av[av.index("--out") + 1]
    assert meta_of(root / "results/smoke/smoke")["smoke_result"] == ("fail" if fail else "pass")
    assert ("FAIL" if fail else "PASS") in capsys.readouterr().out


# ---- AFL-031: ported tester scratch checks (all launches stubbed) ------------------------------

TWO = ["targets/bin/toy_parser", "targets/bin/tlv_parser"]
KINDS = ["first_pilot", "main", "probe", "confirmation_pilot"]


def _opt(argv: list[str], k: str) -> str:
    return argv[argv.index(k) + 1]


def run_argvs(root: Path, monkeypatch: pytest.MonkeyPatch, kind: str) -> list[list[str]]:
    """Run `kind` on two targets with the real `_launch`; only `Popen` of fuzzer.cli is faked."""
    (root / "experiments/configs/main.yaml").write_text(
        cfg_text(targets=TWO, timeout_s=3.25, seconds_per_trial=0.5, concurrency=3))
    to_git(root)
    with rc._chdir(root):
        commit, dirty = rc._provenance()
    seen: list[list[str]] = []
    lock = threading.Lock()
    real = subprocess.Popen

    class P:
        pid = 0

        def __init__(self, argv: list[str], **kw: Any) -> None:
            self.argv, self.returncode = argv, 0

        def communicate(self) -> tuple[str, str]:
            with lock:
                seen.append(self.argv)
            out = Path(_opt(self.argv, "--out"))
            out.mkdir(parents=True)
            (out / "metrics.csv").write_text(METRICS_HEADER + "\n" + metrics_row() + "\n")
            (out / "run.json").write_text(json.dumps({"commit": commit, "dirty": dirty}))
            return "", ""

    def popen(argv: list[str], **kw: Any) -> Any:
        return P(argv) if argv[1:3] == ["-m", "fuzzer.cli"] else real(argv, **kw)
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    monkeypatch.setattr(rc.subprocess, "Popen", popen)
    extra = ["--freeze-commit", "HEAD"] if kind == "main" else []
    assert go(root, "--kind", kind, "--allow-fewer-targets", "two targets", *extra) == 0
    monkeypatch.undo()
    return seen


@pytest.mark.parametrize("kind", KINDS)
def test_every_trial_gets_config_timeout_and_seconds(root: Path, kind: str,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """Kills: `--timeout` dropped from `_launch`'s argv (the CLI would run its default 1.0)."""
    seen = run_argvs(root, monkeypatch, kind)
    assert len(seen) == {"main": 40, "first_pilot": 12, "confirmation_pilot": 12, "probe": 6}[kind]
    for a in seen:
        assert a[1:3] == ["-m", "fuzzer.cli"]
        assert _opt(a, "--timeout") == "3.25" and _opt(a, "--seconds") == "0.5"


@pytest.mark.parametrize("kind", KINDS)
def test_arms_identical_except_schedule_nfr2(root: Path, kind: str,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """Kills: the `--seeds` directory differing per arm (NFR-2)."""
    seen = run_argvs(root, monkeypatch, kind)
    for a in seen:
        t = Path(_opt(a, "--target")).name
        assert _opt(a, "--seeds") == str(root / "targets/seeds" / t)
        if kind == "main":
            assert len(_opt(a, "--freeze-commit")) == 40
        else:
            assert "--freeze-commit" not in a

    def norm(a: list[str]) -> list[str]:
        b = list(a)
        b[b.index("--schedule") + 1] = "X"
        o = b.index("--out") + 1
        b[o] = b[o].replace("/uniform/", "/X/").replace("/fast/", "/X/")
        return b
    u = sorted(norm(a) for a in seen if _opt(a, "--schedule") == "uniform")
    f = sorted(norm(a) for a in seen if _opt(a, "--schedule") == "fast")
    assert u and f
    if kind != "probe":
        assert u == f


def test_symbolizer_gets_config_timeout(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Kills: the symbolizer executor's timeout fixed at 1.0."""
    got: list[float] = []

    class Fake:
        def __init__(self, t: Path, timeout_s: float) -> None:
            got.append(timeout_s)

        def run(self, data: bytes) -> Any:
            raise RuntimeError("stop here")

        def close(self) -> None: ...
    monkeypatch.setattr(rc, "Executor", Fake)
    with pytest.raises(RuntimeError):
        go(root, "--kind", "first_pilot", "--allow-fewer-targets", "x",
           cfg=cfg_text(timeout_s=4.75))
    assert got == [4.75] and no_trials(root)


def test_confirmation_pilot_writes_no_decision(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Kills: the confirmation pilot writing a granularity decision."""
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    monkeypatch.setattr(rc, "_launch", stub_launch(lambda t: {}))  # every trial has a final row
    assert go(root, "--kind", "confirmation_pilot", "--allow-fewer-targets", "x") == 0
    assert len(list((root / "results").rglob("metrics.csv"))) == 6
    assert not list((root / "results").rglob("granularity_decision*.json"))


def test_at_most_concurrency_at_once_and_probe_waves(root: Path, clean_unknown: None,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """Kills: probe trials submitted without a per-wave barrier."""
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    lock = threading.Lock()
    state: dict[str, Any] = {"now": 0, "max": 0, "log": []}
    inner = stub_launch(lambda t: {})

    def fake(t: rc.Trial, *a: Any) -> subprocess.CompletedProcess[str]:
        with lock:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
            state["log"].append(("start", t.wave, time.monotonic()))
        # one slow trial per wave 0: without a barrier wave 1 would start before it ends
        time.sleep(0.4 if (t.wave, t.target, t.schedule) == (0, "toy_parser", "uniform") else 0.05)
        inner(t, *a)
        with lock:
            state["now"] -= 1
            state["log"].append(("end", t.wave, time.monotonic()))
        return subprocess.CompletedProcess([], 0, "", "")
    monkeypatch.setattr(rc, "_launch", fake)
    cfg = cfg_text(targets=TWO, concurrency=3)
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "x", cfg=cfg) == 0
    assert state["max"] == 3
    state.update(now=0, max=0, log=[])
    assert go(root, "--kind", "probe", "--allow-fewer-targets", "x", cfg=cfg) == 0
    assert state["max"] == 3
    end0 = max(ts for ev, w, ts in state["log"] if ev == "end" and w == 0)
    start1 = min(ts for ev, w, ts in state["log"] if ev == "start" and w == 1)
    assert start1 >= end0  # wave 1 starts only after wave 0 is done


@pytest.mark.parametrize("reason", ["", "   "])
def test_allow_fewer_needs_nonempty_reason(root: Path, reason: str,
                                           monkeypatch: pytest.MonkeyPatch,
                                           capsys: pytest.CaptureFixture[str]) -> None:
    """Kills: the empty-reason guard removed (each case alone: the guard's own text)."""
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    monkeypatch.setattr(rc, "_launch", stub_launch(lambda t: {}))
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", reason,
              cfg=cfg_text(targets=TWO)) == 2
    assert "non-empty reason" in capsys.readouterr().err and no_trials(root)


def test_concurrency_eq_cores_ok_above_refused(root: Path, clean_unknown: None,
                                               monkeypatch: pytest.MonkeyPatch,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    """Pins the boundary (c == cores proceeds); kills no mutant the suite misses."""
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    monkeypatch.setattr(rc, "_launch", stub_launch(lambda t: {}))
    monkeypatch.setattr(rc, "physical_cpus", lambda: 5)
    assert go(root, "--kind", "probe", "--allow-fewer-targets", "x",
              cfg=cfg_text(concurrency=6)) == 2
    err = capsys.readouterr().err
    assert "6" in err and "5" in err and no_trials(root)
    assert go(root, "--kind", "probe", "--allow-fewer-targets", "x",
              cfg=cfg_text(concurrency=5)) == 0


# ---- AFL-031: baseline, abort, smoke scratch tests (test_gaps.py) -----------------------------

def test_baseline_probe_summary_label(root: Path, clean_unknown: None,
                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """Kills B2: the baseline label dropped from probe_summary.json."""
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    monkeypatch.setattr(rc, "_launch", stub_launch(lambda t: {}))
    assert go(root, "--kind", "probe", "--baseline", "--allow-fewer-targets", "t") == 0
    s = json.loads((root / "results/probe/unknown/baseline/probe_summary.json").read_text())
    assert s["baseline"] is True and s["label"] == rc.BASELINE_LABEL


def test_dmax_refuses_baseline_json_directly(tmp_path: Path) -> None:
    """Kills B3: the `_dmax` baseline refusal removed (called directly, no dirty-tree mask)."""
    f = tmp_path / "d.json"
    f.write_text(json.dumps({"D_max": 0.1, "baseline": True}))
    with pytest.raises(rc.Refusal, match="baseline"):
        rc._dmax(f)
    f.write_text(json.dumps({"D_max": 0.1}))
    assert rc._dmax(f) == 0.1


GROUP_STUB = textwrap.dedent("""
    import os, subprocess, sys, time
    a = sys.argv
    out = a[a.index("--out") + 1]
    os.makedirs(out)
    g = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)",
                          "stub_trial_grandchild"])
    open(os.path.join(out, "gpid"), "w").write(str(g.pid))
    open(os.path.join(out, "metrics.csv"), "w").write("elapsed_s\\n1\\n")
    time.sleep(60)
""")


def test_abort_reaches_trial_grandchildren(root: Path, tmp_path: Path,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    """Kills A1: `os.kill` instead of `os.killpg` (a trial's own children outlive the abort)."""
    script = tmp_path / "stub_trial_group.py"
    script.write_text(GROUP_STUB)
    real = subprocess.Popen
    monkeypatch.setattr(rc.subprocess, "Popen", lambda argv, **kw: real(
        [sys.executable, str(script), *argv[3:]] if argv[1:3] == ["-m", "fuzzer.cli"] else argv,
        **kw))
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    monkeypatch.setattr(rc, "ABORT_GRACE_S", 1.0)
    threading.Timer(2.0, os.kill, (os.getpid(), signal.SIGTERM)).start()
    t0 = time.monotonic()
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t") == 1
    took = time.monotonic() - t0
    gp = [int(p.read_text()) for p in (root / "results").rglob("gpid")]
    assert len(gp) == 3
    end = time.monotonic() + 3
    while time.monotonic() < end and any(alive(x) for x in gp):
        time.sleep(0.05)
    survivors = [x for x in gp if alive(x)]
    for x in survivors:
        os.kill(x, signal.SIGKILL)
    assert not survivors, "target-like grandchildren outlived the abort"
    assert took < 2.0 + 3 * rc.ABORT_GRACE_S, f"runner held {took:.1f}s by orphaned grandchildren"


def test_grace_is_total_not_per_trial(root: Path, stub_trials: None,
                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """Kills A2: the SIGTERM->SIGKILL grace applied per trial instead of in total."""
    monkeypatch.setenv("STUB_MODE", "ignore,hang")  # every trial is 'fast': all ignore SIGTERM
    t_sig: list[float] = []

    def fire() -> None:
        t_sig.append(time.monotonic())
        os.kill(os.getpid(), signal.SIGINT)
    threading.Timer(2.0, fire).start()
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t",
              cfg=cfg_text(schedules=["fast"])) == 1
    took = time.monotonic() - t_sig[0]
    assert took < 2.0 * rc.ABORT_GRACE_S, f"abort took {took:.2f}s for grace {rc.ABORT_GRACE_S}"


def test_culprit_not_aborted_and_named_in_list(root: Path, stub_trials: None,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """Kills A10: the culprit trial also marked `aborted`."""
    monkeypatch.setenv("STUB_MODE", "fail,hang")
    assert go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t") == 1
    m = meta_of(root / "results/pilot/first_pilot")
    bad = {k: r for k, r in m["trials"].items() if "error" in r}
    assert len(bad) == 1
    ((k, r),) = bad.items()
    assert "aborted" not in r
    assert [e["trial"] for e in m["aborted"]] == [k]


def test_smoke_exit0_without_final_row_fails(root: Path, monkeypatch: pytest.MonkeyPatch,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    """Kills S4: smoke PASS without a final metrics.csv row."""
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    monkeypatch.setattr(rc, "_launch", stub_launch(
        lambda t: None if t.schedule == "fast" else {}))  # fast: header only, exit 0
    assert go(root, "--kind", "smoke", "--allow-fewer-targets", "t") == 1
    assert meta_of(root / "results/smoke/smoke")["smoke_result"] == "fail"
    assert "smoke run: FAIL" in capsys.readouterr().out


def _smoke_with_run_json(root: Path, monkeypatch: pytest.MonkeyPatch, *extra: str) -> None:
    inner = stub_launch(lambda t: {})

    def fake(t: rc.Trial, cfg: rc.Cfg, *a: Any) -> subprocess.CompletedProcess[str]:
        p = inner(t, cfg, *a)
        (t.out / "run.json").write_text(json.dumps({"config": {
            "target": f"targets/bin/{t.target}", "schedule": t.schedule, "seed": t.seed,
            "seconds": cfg.seconds}}))
        (t.out / "crash_events.csv").write_text("elapsed_s,execs,signal,crash_site,path_id,saved\n")
        return p
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    monkeypatch.setattr(rc, "_launch", fake)
    assert go(root, "--kind", "smoke", "--allow-fewer-targets", "t", *extra) == 0


def test_smoke_output_invisible_to_aggregate(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Kills no named mutant: smoke output, default or `--out`, is never analysed."""
    import aggregate as ag
    _smoke_with_run_json(root, monkeypatch)
    _smoke_with_run_json(root, monkeypatch, "--out", str(root / "results/elsewhere"))
    res = root / "results"
    assert len(list(res.rglob("run.json"))) == 4
    assert ag.trial_dirs(res) == [] and ag.main_campaign(res) == {}
    assert not any(ag.is_main_trial(p.parent, res) for p in res.rglob("run.json"))


def test_baseline_with_smoke_kind_refused(root: Path, monkeypatch: pytest.MonkeyPatch,
                                          capsys: pytest.CaptureFixture[str]) -> None:
    """Kills B10: `--baseline` accepted with `--kind smoke`."""
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    monkeypatch.setattr(rc, "_launch", stub_launch(lambda t: {}))
    assert go(root, "--kind", "smoke", "--baseline", "--allow-fewer-targets", "t") == 2
    assert "--baseline" in capsys.readouterr().err and no_trials(root)


def test_exception_after_trial_ran_is_not_recorded_never_started(
        root: Path, stub_trials: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`started` is recorded before launch (AFL-011 known defect); still `aborted`."""
    monkeypatch.setenv("STUB_MODE", "")
    real = rc._launch

    def boom(t: rc.Trial, *a: Any) -> Any:
        p = real(t, *a)
        if (t.schedule, t.seed) == ("uniform", 1007):
            raise RuntimeError("runner bug after the trial ran")
        return p
    monkeypatch.setattr(rc, "_launch", boom)
    with pytest.raises(RuntimeError):
        go(root, "--kind", "first_pilot", "--allow-fewer-targets", "t")
    d = root / "results/pilot/first_pilot"
    rec = meta_of(d)["trials"][str(d / "toy_parser/uniform/s1007")]
    assert (d / "toy_parser/uniform/s1007/pid").exists()  # it did start and run
    assert rec.get("started") is not False, f"record says never started: {rec}"
    assert rec["started"] is True and rec["aborted"] is True and "returncode" not in rec


# ---- AFL-031: P3, crash-probe config record, run-environment record ---------------------------

def _prov(monkeypatch: pytest.MonkeyPatch, dirty: bool | None) -> None:
    monkeypatch.setattr(rc, "_provenance", lambda: ("abc123", dirty))


P3_ARGS = [["--kind", "probe"], ["--crash-probe"], ["--crash-probe", "--baseline"]]


@pytest.mark.parametrize("dirty", [True, None])
@pytest.mark.parametrize("args", P3_ARGS)
def test_probes_refuse_dirty_or_unknown_tree(root: Path, crash_stub: None, args: list[str],
                                             dirty: bool | None, monkeypatch: pytest.MonkeyPatch,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    monkeypatch.setattr(rc, "_launch", stub_launch(lambda t: {}))
    _prov(monkeypatch, dirty)
    assert go(root, *args, "--allow-fewer-targets", "t") == 2
    err = capsys.readouterr().err
    assert "probe refuses a dirty tree" in err and f"dirty={dirty!r}" in err
    assert no_trials(root) and CrashFake.inits == 0


@pytest.mark.parametrize("args", P3_ARGS)
def test_probes_run_on_clean_tree(root: Path, crash_stub: None, args: list[str],
                                  monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    monkeypatch.setattr(rc, "_launch", stub_launch(lambda t: {}))
    _prov(monkeypatch, False)
    assert go(root, *args, "--allow-fewer-targets", "t") == 0


@pytest.mark.parametrize("kind", ["first_pilot", "confirmation_pilot"])
def test_pilots_not_refused_for_dirtiness(root: Path, kind: str, planned: list[rc.Trial],
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    _prov(monkeypatch, True)
    assert go(root, "--kind", kind, "--allow-fewer-targets", "t") == 0 and planned


@pytest.mark.parametrize("baseline", [False, True])
def test_crash_durations_records_config(root: Path, crash_stub: None, baseline: bool,
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    _prov(monkeypatch, False)
    cfg = cfg_text(timeout_s=3.25)
    (root / "experiments/configs/main.yaml").write_text(cfg)
    assert go(root, "--crash-probe", "--allow-fewer-targets", "t",
              *(["--baseline"] if baseline else [])) == 0
    out = root / "results/probe/abc123" / ("baseline_crash" if baseline else "")
    j = json.loads((out / "crash_durations.json").read_text())
    assert j["config_path"] == "experiments/configs/main.yaml"
    assert j["config_sha256"] == hashlib.sha256((root / j["config_path"]).read_bytes()).hexdigest()
    assert j["timeout_s"] == 3.25
    assert {"commit", "dirty", "concurrency", "R", "probe_timeout_s", "hw_physicalcpu", "bugs",
            "D_max", "D_max_bug"} <= set(j) and j["commit"] == "abc123" and j["dirty"] is False


ENV_USER = {"loaded": True, "disabled": False}
ENV_SYSTEM = {"loaded": False, "disabled": True}  # `launchctl print` rc 113: not loaded


def env_cmd(mode: str, calls: list[list[str]]) -> Any:
    """A `_cmd` stub: `ok` gives known answers, `unlisted` lists no overrides, `absent` raises
    OSError, `fail` exits non-zero, `raise`/`timeout` raise UnicodeDecodeError/TimeoutExpired."""
    uid, pgreps = os.getuid(), [0]

    def fake(args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        tool = args[0]
        if tool not in ("launchctl", "pgrep") and not args[-1].startswith("hw.perflevel"):
            return subprocess.CompletedProcess(args, 1, "", "")  # machine(): unrelated
        if mode == "absent":
            raise FileNotFoundError(tool)
        if mode == "raise":
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        if mode == "timeout":
            raise subprocess.TimeoutExpired(args, 10.0)
        if mode == "fail":
            return subprocess.CompletedProcess(args, 2, "garbage", "")
        if args[:2] == ["launchctl", "print"]:
            return subprocess.CompletedProcess(args, 0 if args[2].startswith("gui/") else 113, "", "")
        if args[:2] == ["launchctl", "print-disabled"]:
            lab = ('"com.apple.ReportCrash" => enabled' if args[2] == f"gui/{uid}"
                   else '"com.apple.ReportCrash.Root" => disabled')
            if mode == "unlisted":
                lab = '"com.apple.other" => disabled'
            return subprocess.CompletedProcess(args, 0, f"disabled services = {{\n\t{lab}\n}}\n", "")
        if tool == "pgrep":
            pgreps[0] += 1
            return subprocess.CompletedProcess(args, 0 if pgreps[0] == 1 else 1, "", "")
        return subprocess.CompletedProcess(args, 0, "6\n" if args[-1].endswith("0.physicalcpu")
                                           else "4\n", "")
    return fake


@pytest.mark.parametrize("mode", ["ok", "unlisted", "absent", "fail", "raise", "timeout"])
@pytest.mark.parametrize("args", [["--kind", "probe"], ["--crash-probe"],
                                  ["--kind", "probe", "--baseline"],
                                  ["--crash-probe", "--baseline"]])
def test_run_environment_recorded(root: Path, crash_stub: None, tmp_path: Path, mode: str,
                                  args: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(rc, "check_symbolizer", lambda *a: [])
    monkeypatch.setattr(rc, "_launch", stub_launch(lambda t: {}))
    monkeypatch.setattr(rc, "_cmd", env_cmd(mode, calls))
    _prov(monkeypatch, False)
    out = tmp_path / "out"
    assert go(root, *args, "--allow-fewer-targets", "t", "--out", str(out)) == 0
    j = json.loads((out / ("crash_durations.json" if "--crash-probe" in args
                           else "campaign.json")).read_text())
    if "--crash-probe" not in args:
        assert "finished_at" in j  # a failing command never costs the final write
    if mode in ("ok", "unlisted"):
        user, system, p0, p1 = ENV_USER, ENV_SYSTEM, 6, 4
        if mode == "unlisted":
            user, system = {**ENV_USER, "disabled": False}, {**ENV_SYSTEM, "disabled": False}
        want = {"start": {"user": user, "system": system, "process": True},
                "end": {"user": user, "system": system, "process": False}}
    else:
        null = {"loaded": None, "disabled": None}
        p0 = p1 = None
        want = {w: {"user": null, "system": null, "process": None} for w in ("start", "end")}
    assert j["crash_reporters"] == want
    assert j["hw_perflevel0_physicalcpu"] == p0 and j["hw_perflevel1_physicalcpu"] == p1
    assert j["hw_physicalcpu"] == 8
    assert ["launchctl", "print", "system/com.apple.ReportCrash.Root"] in calls
    assert ["pgrep", "-x", "ReportCrash"] in calls


def test_cmd_has_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """A wedged launchctl must not hang the end-of-run sample: `_cmd` always passes a timeout."""
    seen: dict[str, Any] = {}
    monkeypatch.undo()
    monkeypatch.setattr(rc.subprocess, "run", lambda args, **kw: seen.update(kw))
    rc._cmd(["true"])
    assert seen["timeout"] == rc.CMD_TIMEOUT_S == 10.0
