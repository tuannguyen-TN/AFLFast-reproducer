"""Experiment runner. [implements FR-7 / ticket AFL-011]

Runs N independent trials per (target x schedule) with a fixed wall-clock budget and a distinct
RNG seed per trial, writing per-trial output to results/. Every trial is one `python -m
fuzzer.cli` subprocess (the CLI is run.json's single writer). All pre-registration guards run
before any trial directory exists; none has an override except `--allow-fewer-targets`.

    python harness/run_campaign.py experiments/configs/main.yaml --kind first_pilot
    python harness/run_campaign.py experiments/configs/main.yaml --kind main --freeze-commit H
    python harness/run_campaign.py experiments/configs/main.yaml --kind probe --run-name run1
    python harness/run_campaign.py experiments/configs/main.yaml --crash-probe

Statistics stay out of this file (AFL-012); the pilot rule is a fixed threshold on two medians.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import re
import signal
import statistics
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fuzzer.cli import _provenance, resolve_freeze_commit
from fuzzer.executor import Executor
from fuzzer.fuzzer import crash_site, seed_files
from fuzzer.schedule import SCHEDULES

CAP = 1000  # trials per (target, schedule) per run kind stay below this (AC "Runs >=10 trials")
PILOT_TRIALS = 3
MAIN_MIN_TRIALS = 10  # AC "Runs >=10 trials"
MIN_TARGETS = 3  # PRD s8
# Seed ranges: the AC "Pre-registered target retuning rule and freeze", "Seeds" table.
SEED_OFFSETS = {"main": 0, "first_pilot": 1000, "probe": 2000, "confirmation_pilot": 3000,
                "restarted_first_pilot": 4000, "restarted_confirmation_pilot": 5000,
                "smoke": 9000}
SMOKE_MAX_EXECS = 200  # runner check only: one short trial per (target, schedule)
ABORT_GRACE_S = 10.0  # SIGTERM -> SIGKILL grace for running trials on abort
BASELINE_LABEL = "baseline: informs (d) and c, not used"
CMD_TIMEOUT_S = 10.0  # a wedged launchctl/sysctl must not hang a run (TimeoutExpired is caught)
ENV_ERRORS = (OSError, ValueError, subprocess.SubprocessError)  # run-environment record: null
FIRST_PILOTS = ("first_pilot", "restarted_first_pilot")
CRASH_COLUMNS = ["bug_id", "target", "worker", "round", "concurrency", "outcome", "signal",
                 "wall_s", "crash_site"]


class Refusal(Exception):
    """A pre-flight guard failed: exit non-zero, no trial has run, no trial dir exists."""


# ---- config -------------------------------------------------------------------------------

def _scalar(s: str) -> Any:
    s = s.strip()
    for conv in (int, float):
        try:
            return conv(s)
        except ValueError:
            pass
    return s[1:-1] if len(s) > 1 and s[0] == s[-1] and s[0] in "'\"" else s


def load_yaml(path: Path, text: str | None = None) -> dict[str, Any]:
    """Flat YAML subset: `key: scalar`, `key:` plus `  - item` lines, `#` comments.

    # ponytail: PyYAML is not installed (no installs allowed here); swap for yaml.safe_load.
    """
    out: dict[str, Any] = {}
    key: str | None = None
    for n, raw in enumerate((path.read_text() if text is None else text).splitlines(), 1):
        line = re.sub(r"(^|\s)#.*$", "", raw).rstrip()
        if not line.strip():
            continue
        if "\t" in raw[:len(raw) - len(raw.lstrip())]:
            raise Refusal(f"{path}:{n}: tab in leading whitespace: {raw!r}")
        if line.lstrip().startswith("- "):
            if key is None or not isinstance(out.get(key), list):
                raise Refusal(f"{path}:{n}: list item outside a list: {raw!r}")
            out[key].append(_scalar(line.lstrip()[2:]))
        elif ":" in line and not line.startswith(" "):
            key, _, val = line.partition(":")
            key = key.strip()
            if key in out:
                raise Refusal(f"{path}:{n}: duplicate key {key!r}: {raw!r}")
            out[key] = _scalar(val) if val.strip() else []
        else:
            raise Refusal(f"{path}:{n}: unsupported config line {raw!r}")
    return out


@dataclass(frozen=True)
class Cfg:
    trials: int
    seconds: float
    base_seed: int
    targets: tuple[str, ...]
    schedules: tuple[str, ...]
    timeout_s: float
    concurrency: int


def _num(d: dict[str, Any], k: str, integer: bool, lo: float, strict: bool = False) -> Any:
    v: Any = d.get(k)
    ok = (isinstance(v, int) if integer else isinstance(v, (int, float))) and not isinstance(v, bool)
    if not ok or not math.isfinite(v) or (v <= lo if strict else v < lo):
        want = "integer" if integer else "number"
        raise Refusal(f"config key {k!r} is missing or invalid (need a {want} "
                      f"{'>' if strict else '>='} {lo}, got {v!r})")
    return v


def parse_config(d: dict[str, Any]) -> Cfg:
    """Validate every key; the message names the offending key (AC "Campaign timeout...")."""
    timeout_s = float(_num(d, "timeout_s", False, 0, strict=True))
    conc = _num(d, "concurrency", True, 1)
    trials = _num(d, "trials_per_config", True, 1)
    seconds = float(_num(d, "seconds_per_trial", False, 0, strict=True))
    base = _num(d, "base_seed", True, 0)
    for k in ("targets", "schedules"):
        v = d.get(k)
        if not isinstance(v, list) or not v or not all(isinstance(x, str) for x in v):
            raise Refusal(f"config key {k!r} is missing or invalid (need a non-empty list)")
    bad = [s for s in d["schedules"] if s not in SCHEDULES]
    if bad:
        raise Refusal(f"config key 'schedules' names unknown schedule(s) {bad}")
    return Cfg(trials, seconds, base, tuple(d["targets"]), tuple(d["schedules"]), timeout_s, conc)


# ---- external commands (stubbed in tests) ---------------------------------------------------

def _cmd(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False, timeout=CMD_TIMEOUT_S)


def physical_cpus() -> int:
    """`sysctl -n hw.physicalcpu` as a positive int, else Refusal (never a default)."""
    what = "`sysctl -n hw.physicalcpu`"
    try:
        p = _cmd(["sysctl", "-n", "hw.physicalcpu"])
    except (OSError, subprocess.SubprocessError) as e:  # TimeoutExpired included
        raise Refusal(f"{what} could not run: {e}; refusing to start") from e
    out = p.stdout.strip()
    if p.returncode != 0:
        raise Refusal(f"{what} exited {p.returncode} (output {out!r}); refusing to start")
    if not re.fullmatch(r"[0-9]+", out) or int(out) < 1:
        raise Refusal(f"{what} returned {out!r}, not a positive integer; refusing to start")
    return int(out)


def perf_cores() -> dict[str, int | None]:
    """AC "Run-environment record": P/E core counts; None where sysctl is absent or fails."""
    out: dict[str, int | None] = {}
    for lvl in (0, 1):
        try:
            p = _cmd(["sysctl", "-n", f"hw.perflevel{lvl}.physicalcpu"])
            txt = p.stdout.strip() if p.returncode == 0 else ""
        except ENV_ERRORS:
            txt = ""
        out[f"hw_perflevel{lvl}_physicalcpu"] = int(txt) if re.fullmatch(r"[0-9]+", txt) else None
    return out


def _disabled(domain: str, label: str) -> bool | None:
    try:
        p = _cmd(["launchctl", "print-disabled", domain])
    except ENV_ERRORS:
        return None
    if p.returncode != 0:
        return None
    m = re.search(rf'"{re.escape(label)}"[ \t]*=>[ \t]*(\S*)', p.stdout)
    # unlisted: no disable override in launchd's database, so not disabled; an unrecognised
    # token is unknown (null), never a guessed false (AFL-037 AC 1)
    return {"disabled": True, "true": True, "enabled": False, "false": False}.get(m.group(1)) \
        if m else False


def crash_reporters() -> dict[str, Any]:
    """AC "Run-environment record": both macOS crash reporters (loaded, disabled) and whether a
    ReportCrash process exists; None for what cannot be told. Never stops a run.
    """
    out: dict[str, Any] = {}
    for key, domain, label in (("user", f"gui/{os.getuid()}", "com.apple.ReportCrash"),
                               ("system", "system", "com.apple.ReportCrash.Root")):
        try:
            rc_: int | None = _cmd(["launchctl", "print", f"{domain}/{label}"]).returncode
        except ENV_ERRORS:
            rc_ = None
        out[key] = {"loaded": None if rc_ not in (0, 113) else rc_ == 0,  # 113: not loaded
                    "disabled": _disabled(domain, label)}
    try:
        rc_ = _cmd(["pgrep", "-x", "ReportCrash"]).returncode
    except ENV_ERRORS:
        rc_ = None
    out["process"] = None if rc_ not in (0, 1) else rc_ == 0
    return out


def _first_line(args: list[str]) -> str:
    try:
        p = _cmd(args)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    lines = p.stdout.strip().splitlines()
    return lines[0] if p.returncode == 0 and lines else "unknown"


def machine(hw_physicalcpu: int) -> dict[str, Any]:
    """AC "Campaign machine recorded": exactly these four keys."""
    brew = Path("/opt/homebrew/opt/llvm/bin/clang")  # the compiler targets/Makefile prefers
    cc = str(brew) if brew.exists() else "clang"
    return {"model": _first_line(["sysctl", "-n", "hw.model"]),
            "macos_version": _first_line(["sw_vers", "-productVersion"]),
            "clang_version": _first_line([cc, "--version"]),
            "hw_physicalcpu": hw_physicalcpu}


@contextmanager
def _chdir(p: Path) -> Iterator[None]:
    old = Path.cwd()
    os.chdir(p)
    try:
        yield
    finally:
        os.chdir(old)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


# ---- seed sets and probe layout -------------------------------------------------------------

def probe_layout(pairs: list[tuple[str, str]], c: int) -> list[list[tuple[str, str, int, bool]]]:
    """Waves of exactly `c` trials (target, schedule, i, counted); AC "Waves and fillers".

    Counted trials first (i = 0), then fillers continue the same round-robin cycle with
    i = 1, 2, ...; the last wave is topped up so every counted trial runs at full load.
    """
    p = len(pairs)
    total = c * -(-p // c)
    trials = [(*pairs[k % p], k // p, k < p) for k in range(total)]
    return [trials[w:w + c] for w in range(0, total, c)]


def _pairs(cfg: Cfg, targets: list[str]) -> list[tuple[str, str]]:
    return [(t, s) for t in targets for s in cfg.schedules]  # arms alternate by construction


def seed_sets(cfg: Cfg, targets: list[str]) -> dict[str, set[int]]:
    """Full seed set of every run kind, built from the config (AC "Seed sets disjoint")."""
    out: dict[str, set[int]] = {}
    for kind, off in SEED_OFFSETS.items():
        if kind == "probe":
            waves = probe_layout(_pairs(cfg, targets), cfg.concurrency)
            idx = {i for w in waves for (_, _, i, _) in w}
        else:
            idx = set(range(cfg.trials if kind == "main" else 1 if kind == "smoke" else PILOT_TRIALS))
        out[kind] = {cfg.base_seed + off + i for i in idx}
    return out


def check_caps(cfg: Cfg, targets: list[str]) -> None:
    """Refuse any run kind with CAP or more trials per (target, schedule)."""
    waves = probe_layout(_pairs(cfg, targets), cfg.concurrency)
    probe_n = max(i for w in waves for (_, _, i, _) in w) + 1
    for kind, n in (("main campaign", cfg.trials), ("first pilot", PILOT_TRIALS),
                    ("probe", probe_n), ("smoke", 1), ("confirmation pilot", PILOT_TRIALS),
                    ("restarted first pilot", PILOT_TRIALS),
                    ("restarted confirmation pilot", PILOT_TRIALS)):
        if n >= CAP:
            raise Refusal(f"run kind {kind!r}: {n} trials per (target, schedule) reaches the "
                          f"cap of {CAP}; the seed ranges could meet")


def check_disjoint(cfg: Cfg, targets: list[str]) -> None:
    sets = seed_sets(cfg, targets)
    kinds = list(sets)
    for a in range(len(kinds)):
        for b in range(a + 1, len(kinds)):
            shared = sets[kinds[a]] & sets[kinds[b]]
            if shared:
                raise Refusal(f"seed sets of run kinds {kinds[a]!r} and {kinds[b]!r} overlap "
                              f"(shared seed {min(shared)})")


# ---- pre-flight checks ----------------------------------------------------------------------

def check_targets(cfg: Cfg, root: Path, allow_fewer: str | None) -> list[str]:
    """Distinct target names; refuse <3 without the recorded override (PRD s8) or a missing binary."""
    names = list(dict.fromkeys(Path(t).name for t in cfg.targets))
    if len(names) < MIN_TARGETS and not allow_fewer:
        raise Refusal(f"PRD s8 requires >= {MIN_TARGETS} distinct targets, config has "
                      f"{len(names)}; use --allow-fewer-targets \"<reason>\" to override")
    for t in dict.fromkeys(cfg.targets):
        p = root / t
        launched = root / "targets/bin" / Path(t).name  # what _launch and the symbolizer run
        if os.path.normpath(p) != os.path.normpath(launched):
            raise Refusal(f"target {t!r} resolves to {p}, but trials launch {launched}; "
                          "configure targets as targets/bin/<name>")
        if not (p.is_file() and os.access(p, os.X_OK)):
            raise Refusal(f"target binary {p} does not exist or is not executable")
    return names


def check_s0(names: list[str], root: Path) -> dict[str, dict[str, Any]]:
    """S0 integrity (hash, non-empty, seeds dir holds only S0); returns the corpus record."""
    sums_path = root / "targets/seeds/SHA256SUMS"
    if not sums_path.is_file():
        raise Refusal(f"{sums_path} is missing")
    sums = {}
    for ln in sums_path.read_text().splitlines():
        m = re.fullmatch(r"([0-9a-f]{64})  (\S+)", ln.strip())
        if m:
            sums[m.group(2)] = m.group(1)
    rec: dict[str, dict[str, Any]] = {}
    for n in names:
        d = root / "targets/seeds" / n
        s0 = d / "S0"
        try:
            data = s0.read_bytes()
            others = [p.name for p in seed_files(d) if p.name != "S0"]
        except OSError as e:
            raise Refusal(f"target {n}: S0 missing or unreadable ({e})") from e
        if others:
            raise Refusal(f"target {n}: seeds dir holds unexpected files {others} (only S0)")
        # AFL-011 (origin AFL-019): non-empty S0 + no operator empties a non-empty input
        # => mutate(b"") is unreachable in a campaign.
        if not data:
            raise Refusal(f"target {n}: seed file S0 is empty")
        got = hashlib.sha256(data).hexdigest()
        want = sums.get(f"{n}/S0")
        if want is None:
            raise Refusal(f"target {n}: no line for {n}/S0 in {sums_path}")
        if got != want:
            raise Refusal(f"target {n}: S0 hash {got} != expected {want}")
        rec[n] = {"dir": str(d), "files": [{"name": "S0", "sha256": got}]}
    return rec


def load_bugs(names: list[str], root: Path) -> list[tuple[str, dict[str, str], bytes]]:
    """(bug id, ground-truth entry, trigger bytes) for every bug of the campaign's targets."""
    tdir = root / "targets"
    gt = json.loads((tdir / "ground_truth.json").read_text())
    tpath = tdir / "triggers.json"
    if not tpath.is_file():
        raise Refusal("targets/triggers.json is missing")
    trig = json.loads(tpath.read_text())
    out = []
    for bid, e in gt.items():
        if e["target"] not in names:
            continue
        try:
            out.append((bid, e, bytes.fromhex(trig[bid])))
        except (KeyError, ValueError) as ex:
            raise Refusal(f"bug {bid}: no valid hex trigger in targets/triggers.json "
                          f"({type(ex).__name__})") from ex
    return out


def check_symbolizer(names: list[str], root: Path, timeout_s: float) -> list[str]:
    """One trigger per bug through the executor; crash_site() must equal the bug's function."""
    bugs = load_bugs(names, root)
    failures, checked = [], []
    for target in names:
        ex = Executor(root / "targets/bin" / target, timeout_s)
        try:
            for bid, e, data in bugs:
                if e["target"] != target:
                    continue
                site = crash_site(ex.run(data).stderr, e["file"])
                checked.append(bid)
                if site != e["function"]:
                    failures.append(f"{bid}: input {data.hex()}, expected {e['function']!r}, "
                                    f"got {site!r}")
        finally:
            ex.close()
    if failures:
        raise Refusal("ASan symbolization is not working (llvm-symbolizer missing or failing, or "
                      "target built without -g): " + "; ".join(failures))
    return checked


def check_floor(timeout_s: float, k: float, dmaxes: list[float]) -> None:
    """Item (h): timeout_s >= k x D_max for every run counted."""
    if k <= 1:
        raise Refusal(f"--k must be > 1, got {k}")
    if not dmaxes:
        raise Refusal("--k needs at least one D_max (--dmax-json, or --crash-probe)")
    if timeout_s < k * max(dmaxes):
        raise Refusal(f"timeout_s {timeout_s} < k x D_max = {k} x {max(dmaxes)}")


# ---- output ---------------------------------------------------------------------------------

def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, default=str))
    os.replace(tmp, path)


def final_row(trial_dir: Path) -> dict[str, float] | None:
    """Last row of a trial's metrics.csv, numeric; None if absent (e.g. killed trial)."""
    try:
        with (trial_dir / "metrics.csv").open(newline="") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return None
    try:
        return {k: float(v) for k, v in rows[-1].items()} if rows else None
    except (ValueError, TypeError):  # half-written last row of a killed trial
        return None


def granularity_decision(trial_dirs: list[tuple[str, Path]]) -> dict[str, Any]:
    """Pre-registered fallback trigger, pooled over both arms, per target (ADR-0001)."""
    per: dict[str, dict[str, list[float]]] = {}
    for target, d in trial_dirs:
        r = final_row(d)
        if r:
            m = per.setdefault(target, {"paths": [], "corpus": []})
            m["paths"].append(r["distinct_path_ids"])
            m["corpus"].append(r["corpus_size"])
    targets = {}
    for t, m in per.items():
        mp, mc = statistics.median(m["paths"]), statistics.median(m["corpus"])
        targets[t] = {"median_distinct_path_ids": mp, "median_corpus_size": mc,
                      "trigger": mp < 2 * mc or mp < 20}
    fired = any(v["trigger"] for v in targets.values())
    return {"targets": targets, "trigger_fired": fired,
            "granularity": "hit_count_buckets" if fired else "presence_only"}


# ---- trials ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class Trial:
    target: str
    schedule: str
    seed: int
    out: Path
    wave: int = 0
    counted: bool = True
    max_execs: int | None = None


_ABORT = threading.Event()  # set once the campaign aborts; _launch refuses to outlive it
_PROCS: set["subprocess.Popen[str]"] = set()  # running trial processes, guarded by _PROCS_LOCK
_PROCS_LOCK = threading.Lock()


def abort_trials() -> None:
    """Abort: SIGTERM every running trial, wait ABORT_GRACE_S in total, SIGKILL the survivors."""
    _ABORT.set()
    with _PROCS_LOCK:
        procs = list(_PROCS)
    for p in procs:
        _signal_group(p, signal.SIGTERM)
    deadline = time.monotonic() + ABORT_GRACE_S
    for p in procs:
        try:
            p.wait(max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
        _signal_group(p, signal.SIGKILL)  # survivors, and any target process left in the group


def _signal_group(p: "subprocess.Popen[str]", sig: int) -> None:
    """Signal the trial's whole process group (each trial is its own session leader)."""
    if p.pid <= 1:  # never signal our own group (pid 0) or init
        return
    try:
        os.killpg(p.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _launch(t: Trial, cfg: Cfg, root: Path, freeze: str | None) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, "-m", "fuzzer.cli", "--target", str(root / "targets/bin" / t.target),
            "--schedule", t.schedule, "--seconds", str(cfg.seconds), "--seed", str(t.seed),
            "--out", str(t.out), "--seeds", str(root / "targets/seeds" / t.target),
            "--timeout", str(cfg.timeout_s)]  # never the CLI's default of 1.0
    if freeze:
        argv += ["--freeze-commit", freeze]
    if t.max_execs is not None:
        argv += ["--max-execs", str(t.max_execs)]
    old = os.environ.get("PYTHONPATH", "")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(SRC), old] if old else [str(SRC)])}
    p = subprocess.Popen(argv, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, start_new_session=True)
    with _PROCS_LOCK:
        _PROCS.add(p)
        if _ABORT.is_set():  # abort raced with this launch: no work done yet, no grace needed
            _signal_group(p, signal.SIGKILL)
    try:
        out, err = p.communicate()  # drains both pipes: no deadlock on a chatty trial
    finally:
        with _PROCS_LOCK:
            _PROCS.discard(p)
    return subprocess.CompletedProcess(argv, p.returncode, out, err)


def plan(kind: str, cfg: Cfg, names: list[str], run_dir: Path) -> list[Trial]:
    off = cfg.base_seed + SEED_OFFSETS[kind]

    def mk(t: str, s: str, i: int, wave: int = 0, counted: bool = True) -> Trial:
        return Trial(t, s, off + i, run_dir / t / s / f"s{off + i}", wave, counted)

    if kind == "probe":
        return [mk(t, s, i, w, counted) for w, wave in
                enumerate(probe_layout(_pairs(cfg, names), cfg.concurrency))
                for (t, s, i, counted) in wave]
    if kind == "smoke":
        return [replace(mk(t, s, 0), max_execs=SMOKE_MAX_EXECS) for t in names for s in cfg.schedules]
    n = cfg.trials if kind == "main" else PILOT_TRIALS
    return [mk(t, s, i) for i in range(n) for t in names for s in cfg.schedules]


def execute(kind: str, trials: list[Trial], cfg: Cfg, root: Path, freeze: str | None,
            start_commit: str, meta: dict[str, Any], meta_path: Path) -> bool:
    """Run trials at most `cfg.concurrency` at once; False if the campaign aborted.

    On abort (a bad trial, or `_ABORT` set by a signal) running trials get SIGTERM then SIGKILL
    (`abort_trials`); they and every not-yet-started trial are recorded `aborted`.
    """
    lock = threading.Lock()
    results: dict[str, Any] = meta["trials"]

    def one(t: Trial) -> None:
        try:
            _one(t)
        except BaseException:  # fatal runner error once a trial may be running: stop them all
            abort_trials()
            raise

    def _one(t: Trial) -> None:
        rec: dict[str, Any] = {"target": t.target, "schedule": t.schedule, "seed": t.seed,
                               "wave": t.wave, "counted": t.counted}
        if _ABORT.is_set():
            with lock:
                results[str(t.out)] = {**rec, "aborted": True, "started": False}
                _write_json(meta_path, meta)
            return
        with lock:  # (AFL-031) `started` is on the record before `_launch`; the handler keeps it
            results[str(t.out)] = {**rec, "started": True}
        p = _launch(t, cfg, root, freeze)
        rec["started"] = True
        rec["returncode"] = p.returncode
        bad = None
        if p.returncode != 0:
            bad = f"trial exited {p.returncode}: {p.stderr.strip()[-300:]}"
        elif kind == "main":  # AC Clean-tree provenance (b): one commit per campaign
            try:
                rj = json.loads((t.out / "run.json").read_text())
            except (OSError, ValueError):
                rj = {}
            if rj.get("commit") != start_commit or rj.get("dirty") is not False:
                bad = (f"run.json commit {rj.get('commit')!r} dirty {rj.get('dirty')!r}, "
                       f"campaign started at {start_commit}")
        culprit = False
        with lock:
            if bad and _ABORT.is_set():  # killed by, or failing during, someone else's abort
                rec["aborted"] = True
            elif bad:
                culprit = True
                _ABORT.set()
                rec["error"] = bad
                meta.setdefault("aborted", []).append({"trial": str(t.out), "error": bad})
                print(f"error: trial {t.out}: {bad}", file=sys.stderr)
            results[str(t.out)] = rec
            _write_json(meta_path, meta)
        if culprit:
            abort_trials()

    def run_all(batch: list[Trial]) -> None:
        with ThreadPoolExecutor(cfg.concurrency) as pool:
            try:
                list(pool.map(one, batch))
            except BaseException:  # abort before the pool waits for its running trials
                abort_trials()
                raise

    try:
        if kind == "probe":  # full waves: every counted trial runs at full load
            for w in sorted({t.wave for t in trials}):
                run_all([t for t in trials if t.wave == w])
        else:
            run_all(trials)
    except BaseException as e:
        with lock:
            for t in trials:
                r = results.setdefault(str(t.out), {"target": t.target, "schedule": t.schedule,
                                                    "seed": t.seed, "wave": t.wave,
                                                    "counted": t.counted, "aborted": True,
                                                    "started": False})
                if "returncode" not in r:  # launched, no outcome recorded: excluded (AFL-012)
                    r["aborted"] = True
            meta.setdefault("aborted", []).append(
                {"trial": None, "error": f"runner error {type(e).__name__}: {e}"})
            _write_json(meta_path, meta)
        raise
    return not _ABORT.is_set()


def probe_summary(trials: list[Trial], timeout_s: float) -> dict[str, Any]:
    """Per-trial exec/s, hangs, hang_time_s, overhead (Timing-probe additions); hang rule."""
    rows: list[dict[str, Any]] = []
    for t in trials:
        r = final_row(t.out)
        if r is None:
            continue
        hangs, ht = r["hangs"], r["hang_time_s"]
        rows.append({"target": t.target, "schedule": t.schedule, "seed": t.seed, "wave": t.wave,
                     "role": "counted" if t.counted else "filler, not used",
                     "execs": r["execs"], "elapsed_s": r["elapsed_s"],
                     "exec_per_s": r["execs"] / r["elapsed_s"] if r["elapsed_s"] else 0.0,
                     "hangs": hangs, "hang_rate": hangs / r["execs"] if r["execs"] else 0.0,
                     "hang_time_s": ht, "hang_overhead_s": ht - hangs * timeout_s,
                     "hang_overhead_per_hang_s": (ht - hangs * timeout_s) / hangs if hangs else None})
    return {"rows": rows, "hang_rule_violated": any(r["hangs"] > 0 for r in rows)}


# ---- crash-duration measurement -------------------------------------------------------------

def crash_probe(cfg: Cfg, names: list[str], root: Path, out: Path, rounds: int,
                probe_timeout_s: float, hw: int, commit: str, dirty: bool | None,
                k: float | None, cfg_path: Path, cfg_sha256: str,
                start_reporters: dict[str, Any], baseline: bool = False) -> None:
    """`--crash-probe`: every bug's trigger, `c` workers x `rounds`; no trial directory."""
    reporters = {"start": start_reporters}
    bugs = load_bugs(names, root)
    rows: list[list[Any]] = []
    lock = threading.Lock()

    def worker(w: int) -> None:
        by_target: dict[str, Executor] = {}
        try:
            for rnd in range(rounds):
                for bid, e, data in bugs:
                    ex = by_target.get(e["target"])
                    if ex is None:
                        ex = by_target[e["target"]] = Executor(
                            root / "targets/bin" / e["target"], probe_timeout_s)
                    r = ex.run(data)
                    site = crash_site(r.stderr, e["file"])
                    with lock:
                        rows.append([bid, e["target"], w, rnd, cfg.concurrency, r.outcome,
                                     r.signal, r.exec_time, site])
        finally:
            for ex in by_target.values():
                ex.close()

    with ThreadPoolExecutor(cfg.concurrency) as pool:
        for f in [pool.submit(worker, w) for w in range(cfg.concurrency)]:
            f.result()
    order = {b[0]: n for n, b in enumerate(bugs)}
    rows.sort(key=lambda r: (order[r[0]], r[2], r[3]))
    out.mkdir(parents=True, exist_ok=True)
    with (out / "crash_durations.csv").open("w", newline="") as fh:
        cw = csv.writer(fh)
        cw.writerow(CRASH_COLUMNS)
        cw.writerows(rows)
    fn = {b[0]: b[1]["function"] for b in bugs}
    for r in rows:  # Validity: a timed-out run's duration is censored, so no D_max
        if r[5] != "crash" or r[6] != 6 or r[8] != fn[r[0]]:
            raise Refusal(f"crash probe invalid for bug {r[0]}: row {dict(zip(CRASH_COLUMNS, r))}")
    per_bug = {}
    for bid, *_ in bugs:
        ws = [r[7] for r in rows if r[0] == bid]
        per_bug[bid] = {"runs": len(ws), "median_wall_s": statistics.median(ws),
                        "max_wall_s": max(ws)}
    top = max(rows, key=lambda r: r[7])
    reporters["end"] = crash_reporters()
    _write_json(out / "crash_durations.json", {
        "commit": commit, "dirty": dirty, "concurrency": cfg.concurrency, "R": rounds,
        "probe_timeout_s": probe_timeout_s, "hw_physicalcpu": hw, **perf_cores(),
        "crash_reporters": reporters, "bugs": per_bug, "D_max": top[7], "D_max_bug": top[0],
        "config_path": os.path.relpath(cfg_path, root),
        "config_sha256": cfg_sha256,
        "timeout_s": cfg.timeout_s,
        **({"baseline": True, "label": BASELINE_LABEL} if baseline else {})})
    if k is not None and not baseline:  # the baseline's D_max never feeds the floor
        check_floor(cfg.timeout_s, k, [top[7]])


# ---- main -----------------------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="run_campaign", description="AFL-011 campaign runner.")
    p.add_argument("config", type=Path)
    p.add_argument("--kind", choices=sorted(SEED_OFFSETS), default="main")
    p.add_argument("--crash-probe", action="store_true")
    p.add_argument("--rounds", type=int, default=1, help="crash probe rounds R (>= 1)")
    p.add_argument("--probe-timeout", type=float, default=30.0, help="crash probe executor timeout")
    p.add_argument("--baseline", action="store_true",
                   help="concurrency-1 baseline (with --kind probe or --crash-probe): c = 1")
    p.add_argument("--allow-fewer-targets", metavar="REASON", default=None)
    p.add_argument("--freeze-commit", metavar="HASH", default=None)
    p.add_argument("--run-name", default=None, help="probe run directory name (default: kind)")
    p.add_argument("--out", type=Path, default=None, help="run directory (default under results/)")
    p.add_argument("--k", type=float, default=None, help="margin: require timeout_s >= k x D_max")
    p.add_argument("--dmax-json", type=Path, action="append", default=[],
                   help="crash_durations.json of an official run counted for the floor")
    return p


def _dmax(p: Path) -> float:
    try:
        v = json.loads(p.read_text())["D_max"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise Refusal(f"--dmax-json {p}: cannot read key 'D_max' ({type(e).__name__}: {e})") from e
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise Refusal(f"--dmax-json {p}: 'D_max' is not a finite number ({v!r})")
    if json.loads(p.read_text()).get("baseline"):
        raise Refusal(f"--dmax-json {p}: a baseline D_max never feeds the timeout floor")
    return float(v)


def _preflight(a: argparse.Namespace, root: Path) -> tuple[Cfg, list[str], dict[str, Any], int, str]:
    cfg_path = a.config if a.config.is_absolute() else root / a.config
    if not cfg_path.is_file():
        raise Refusal(f"config {cfg_path} not found")
    campaign = a.kind == "main" and not a.crash_probe
    if campaign and cfg_path.resolve() != (root / "experiments/configs/main.yaml").resolve():
        raise Refusal(f"--kind main runs only experiments/configs/main.yaml (the frozen file), "
                      f"got {cfg_path}")
    raw = cfg_path.read_bytes()  # hashed and parsed from the same bytes (AFL-037 AC 3)
    cfg = parse_config(load_yaml(cfg_path, raw.decode()))
    if a.baseline:
        if not (a.crash_probe or a.kind == "probe"):
            raise Refusal("--baseline needs --kind probe or --crash-probe")
        if a.k is not None or a.dmax_json:
            raise Refusal("--baseline measures are never part of the timeout floor: "
                          "no --k / --dmax-json")
        cfg = replace(cfg, concurrency=1)  # whatever main.yaml says
    if campaign and cfg.trials < MAIN_MIN_TRIALS:
        raise Refusal(f"main campaign needs trials_per_config >= {MAIN_MIN_TRIALS}, "
                      f"got {cfg.trials}")
    if a.allow_fewer_targets is not None and not a.allow_fewer_targets.strip():
        raise Refusal("--allow-fewer-targets needs a non-empty reason")
    names = check_targets(cfg, root, a.allow_fewer_targets)
    check_caps(cfg, names)
    check_disjoint(cfg, names)
    hw = physical_cpus()
    if cfg.concurrency > hw:
        raise Refusal(f"concurrency {cfg.concurrency} exceeds hw.physicalcpu {hw}")
    if a.k is not None:
        floors = [_dmax(p) for p in a.dmax_json]
        if floors or not a.crash_probe:  # the crash probe adds its own D_max afterwards
            check_floor(cfg.timeout_s, a.k, floors)
    elif a.dmax_json:
        raise Refusal("--dmax-json needs --k")
    if a.crash_probe and a.rounds < 1:
        raise Refusal(f"--rounds must be >= 1, got {a.rounds}")
    corpus = check_s0(names, root)
    return cfg, names, corpus, hw, hashlib.sha256(raw).hexdigest()


def run(argv: list[str], root: Path = ROOT) -> int:
    a = _parser().parse_args(argv)
    cfg_path = a.config if a.config.is_absolute() else root / a.config
    try:
        cfg, names, corpus, hw, cfg_sha = _preflight(a, root)
        with _chdir(root):
            commit, dirty = _provenance()
            if a.crash_probe and commit == "unknown":
                raise Refusal("crash probe needs a known commit (HEAD is unknown); "
                              "its output is keyed by commit")
            freeze: str | None = None
            campaign = a.kind == "main" and not a.crash_probe
            if (campaign or a.crash_probe or a.kind == "probe") and dirty is not False:
                st = _git(root, "status", "--porcelain", "--untracked-files=no").stdout
                raise Refusal(f"{'main campaign' if campaign else 'probe'} refuses a dirty tree "
                              f"(dirty={dirty!r}); modified tracked files:\n" + st)  # P3
            if campaign:
                if not a.freeze_commit:
                    raise Refusal("main campaign requires --freeze-commit HASH")
                try:
                    freeze = resolve_freeze_commit(a.freeze_commit)
                except ValueError as e:
                    raise Refusal(str(e)) from e
                if _git(root, "diff", "--quiet", freeze, "HEAD", "--", "targets/",
                        "experiments/configs/main.yaml").returncode != 0:
                    raise Refusal(f"targets/ or main.yaml changed since freeze commit {freeze}")
        # before the symbolizer check: it crashes every bug's trigger once, which could itself
        # make `process` true at start (AFL-037 AC 2)
        start_reporters = crash_reporters()
        check_symbolizer(names, root, cfg.timeout_s)  # last: it executes the binaries
    except Refusal as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if a.crash_probe:
        out = a.out or root / "results/probe" / commit / ("baseline_crash" if a.baseline else "")
        try:
            if any((out / n).exists() for n in ("crash_durations.csv", "crash_durations.json")):
                raise Refusal(f"crash-measurement output already exists in {out}; "
                              "never overwritten")
            crash_probe(cfg, names, root, out, a.rounds, a.probe_timeout, hw, commit, dirty, a.k,
                        cfg_path, cfg_sha, start_reporters, a.baseline)
        except Refusal as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        return 0

    base = {"main": "results/main", "probe": f"results/probe/{commit}",
            "smoke": "results/smoke"}.get(a.kind, "results/pilot")
    name = a.run_name or ("baseline" if a.baseline else a.kind)
    default = root / base / name if a.kind != "main" else root / base
    run_dir = a.out or default
    if run_dir.exists() and any(run_dir.iterdir()):
        print(f"error: run directory {run_dir} exists and is not empty", file=sys.stderr)
        return 2
    decision = run_dir.parent / ("granularity_decision.json" if a.kind == "first_pilot" else
                                 "granularity_decision_restarted.json")
    if a.kind in FIRST_PILOTS and decision.exists():
        print(f"error: {decision} already exists; the decision is written once, never "
              "overwritten", file=sys.stderr)
        return 2
    trials = plan(a.kind, cfg, names, run_dir)
    meta: dict[str, Any] = {
        "kind": a.kind, "command": [sys.executable, str(Path(__file__).resolve()), *argv],
        "commit": commit, "dirty": dirty, "started_at": datetime.now(timezone.utc).isoformat(),
        "config": {**cfg.__dict__, "targets": list(cfg.targets), "schedules": list(cfg.schedules)},
        "timeout_s": cfg.timeout_s, "concurrency": cfg.concurrency, "hw_physicalcpu": hw,
        **perf_cores(), "crash_reporters": {"start": start_reporters},
        "machine": machine(hw), "targets": names, "seed_corpus": corpus,
        "seed_sets": {k: sorted(v) for k, v in seed_sets(cfg, names).items()},
        "allow_fewer_targets": a.allow_fewer_targets, "freeze_commit": freeze, "trials": {}}
    if a.kind == "smoke":
        meta["excluded_from_analysis"] = True  # runner check only
    if a.baseline:
        meta.update(baseline=True, label=BASELINE_LABEL)
    meta_path = run_dir / "campaign.json"
    _write_json(meta_path, meta)  # before any trial: a killed campaign keeps its record
    got: list[int] = []

    def on_signal(signum: int, _frame: Any) -> None:
        got.append(signum)
        abort_trials()

    _ABORT.clear()  # before the handlers: a signal arriving after this must not be lost
    old = {s: signal.signal(s, on_signal) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        ok = execute(a.kind, trials, cfg, root, freeze, commit, meta, meta_path)
    finally:
        for s, h in old.items():
            signal.signal(s, h)
    if got:
        ok = False
        meta.setdefault("aborted", []).append(
            {"trial": None, "error": f"runner received signal {signal.Signals(got[0]).name}"})
    if a.kind in FIRST_PILOTS:
        missing = [str(t.out) for t in trials if final_row(t.out) is None]
        if ok and not missing:
            _write_json(decision, granularity_decision([(t.target, t.out) for t in trials]))
        else:
            print(f"error: {decision.name} not written; pilot "
                  f"{'completed' if ok else 'aborted'}, trials without a final row: {missing}",
                  file=sys.stderr)
            ok = False
    if a.kind == "probe":
        summ = probe_summary(trials, cfg.timeout_s)
        if a.baseline:
            summ.update(baseline=True, label=BASELINE_LABEL)
        _write_json(run_dir / "probe_summary.json", summ)
        if summ["hang_rule_violated"]:
            print("error: Hang rule: a probe trial hung; do not freeze (AFL-011)", file=sys.stderr)
            ok = False
    if a.kind == "smoke":  # pass: every trial exited 0 (ok) and has a final metrics row
        passed = ok and all(final_row(t.out) is not None for t in trials)
        meta["smoke_result"] = "pass" if passed else "fail"
        print(f"smoke run: {'PASS' if passed else 'FAIL'}")
        ok = passed
    meta["crash_reporters"]["end"] = crash_reporters()
    meta["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(meta_path, meta)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    return run(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    sys.exit(main())
