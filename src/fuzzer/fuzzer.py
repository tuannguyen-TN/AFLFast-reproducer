"""Main fuzzing loop. [implements FR-1..5, FR-8 / ticket AFL-007, ADR-0004, ADR-0005]

Mutation is blind (CLAUDE.md s2): coverage reaches only `corpus.observe` (retention, f(i))
and, through the schedule, the energy. The mutator sees bytes and the one RNG, nothing else.
The arms differ only in `schedule.SCHEDULES[cfg.schedule]`; no other branch reads it.
"""
import csv
import json
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from fuzzer import coverage, mutator
from fuzzer.corpus import Corpus
from fuzzer.executor import ExecResult, Executor
from fuzzer.schedule import SCHEDULES

METRICS_COLUMNS = ["elapsed_s", "execs", "edges", "corpus_size", "distinct_path_ids",
                   "crash_events", "crashes_saved", "hangs", "hang_time_s"]
CRASH_COLUMNS = ["elapsed_s", "execs", "signal", "crash_site", "path_id", "saved"]
SENTINELS = frozenset({"no_stack", "unsymbolized", "no_target_frame"})

_FRAME = re.compile(rb"^\s*#\d+ 0x[0-9a-fA-F]+ (.*)$")
_SYMBOLIZED = re.compile(rb"^in (\S+?)(?:\+0x[0-9a-fA-F]+)? (.*)$")


@dataclass(frozen=True)
class FuzzConfig:
    target: Path
    schedule: str  # "uniform" | "fast"
    seconds: float
    seed: int
    out_dir: Path
    seeds_dir: Path  # holds S0 (ADR-0004 s6)
    max_execs: int | None = None
    timeout_s: float = 1.0


def seed_files(seeds_dir: Path) -> list[Path]:
    """Non-hidden regular files of `seeds_dir`, sorted by name (ADR-0005 s1). May be empty."""
    return sorted((p for p in Path(seeds_dir).iterdir()
                   if p.is_file() and not p.name.startswith(".")), key=lambda p: p.name)


def validate_config(cfg: FuzzConfig) -> None:
    """Raise ValueError on the first bad parameter (ADR-0005 s2). No side effects."""
    if cfg.max_execs is not None and cfg.max_execs < 1:
        raise ValueError(f"max_execs must be >= 1, got {cfg.max_execs}")
    if cfg.seconds <= 0:
        raise ValueError(f"seconds must be > 0, got {cfg.seconds}")
    if cfg.timeout_s <= 0:
        raise ValueError(f"timeout_s must be > 0, got {cfg.timeout_s}")


def crash_site(stderr: bytes, source: str) -> str:
    """Crash site = function of the first frame of the first ASan stack located in `source`.

    `source` is the target's source file name (e.g. "tlv_parser.c"). Runtime/interceptor and
    libc frames never match it, so they are skipped. Never returns "": sentinels are
    "no_stack" (no frames), "unsymbolized" (frames without function names) and
    "no_target_frame" (symbolized, none in `source`). [AFL-007; shared with AFL-013]
    """
    frames: list[bytes] = []
    for line in stderr.splitlines():
        m = _FRAME.match(line)
        if m:
            frames.append(m.group(1))
        elif frames:
            break  # first stack only: later "#0" lines belong to the stack-frame description
    if not frames:
        return "no_stack"
    parsed = [m for m in map(_SYMBOLIZED.match, frames) if m]
    if not parsed:
        return "unsymbolized"
    for m in parsed:
        loc = m.group(2).split(b":")[0].rsplit(b"/", 1)[-1]
        if loc == source.encode():
            return m.group(1).decode()
    return "no_target_frame"


class _Recorder:
    """Writes metrics.csv, crash_events.csv and crashes/ (FR-8, AFL-007 storage rule)."""

    def __init__(self, out_dir: Path) -> None:
        self.out = out_dir
        self._files: list[IO[str]] = []
        self._metrics = self._open("metrics.csv", METRICS_COLUMNS)
        self._events = self._open("crash_events.csv", CRASH_COLUMNS)
        self.crash_events = 0
        self.saved = 0
        self.hangs = 0
        self.hang_time_s = 0.0  # wall-clock; feeds no decision
        self.path_ids: set[int] = set()  # lookup/len only
        self._crash_paths: set[int] = set()
        self._crash_sites: set[str] = set()
        self._last: tuple[int, int, int] | None = None

    def _open(self, name: str, cols: list[str]) -> Any:
        f = (self.out / name).open("w", newline="", buffering=1)  # AFL-011: rows survive SIGKILL
        self._files.append(f)
        w = csv.writer(f)
        w.writerow(cols)
        return w

    def crash(self, data: bytes, r: ExecResult, site: str, elapsed: float, execs: int) -> None:
        pid = coverage.path_id(r.edges)
        self.crash_events += 1
        saved = ""
        if pid not in self._crash_paths or site not in self._crash_sites:
            self._crash_paths.add(pid)
            self._crash_sites.add(site)
            d = self.out / "crashes"
            d.mkdir(exist_ok=True)
            (d / f"{self.saved:06d}.bin").write_bytes(data)
            (d / f"{self.saved:06d}.json").write_text(json.dumps({
                "elapsed_s": elapsed, "execs": execs, "signal": r.signal,
                "exit_status": r.exit_status, "path_id": pid, "crash_site": site,
                "stderr": r.stderr.decode("utf-8", "replace")}))
            saved = f"crashes/{self.saved:06d}.bin"
            self.saved += 1
        self._events.writerow([elapsed, execs, r.signal, site, pid, saved])

    def tick(self, elapsed: float, execs: int, corpus: Corpus, final: bool = False) -> None:
        """One metrics row on any change to edges / corpus size / crash events (or `final`)."""
        state = (len(corpus.seen), len(corpus.seeds), self.crash_events)
        if state != self._last or final:
            self._last = state
            self._metrics.writerow([elapsed, execs, *state[:2], len(self.path_ids),
                                    self.crash_events, self.saved, self.hangs,
                                    self.hang_time_s])

    def close(self) -> None:
        for f in self._files:
            f.close()


def run(cfg: FuzzConfig) -> None:
    """Run one fuzzing trial; stops at `seconds` (time.monotonic) or `max_execs`."""
    validate_config(cfg)
    paths = seed_files(cfg.seeds_dir)
    if not paths:
        raise ValueError(f"no seed files in {cfg.seeds_dir}")
    seeds = [p.read_bytes() for p in paths]
    assign_energy = SCHEDULES[cfg.schedule]  # the only use of cfg.schedule (NFR-2)
    rng = random.Random(cfg.seed)  # the only RNG (NFR-1)
    # relies on the Makefile `bin/%: %.c` rule: a new target <name> must have source <name>.c
    source = Path(cfg.target).name + ".c"
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    executor = Executor(cfg.target, cfg.timeout_s)
    rec: _Recorder | None = None
    try:
        corpus = Corpus(cfg.out_dir)
        execs = 0
        start = time.monotonic()  # ADR-0005 s2: just before S0, setup excluded

        def spent() -> bool:
            return ((cfg.max_execs is not None and execs >= cfg.max_execs)
                    or time.monotonic() - start >= cfg.seconds)

        def execute(data: bytes) -> tuple[ExecResult, float]:
            nonlocal execs
            r = executor.run(data)
            execs += 1
            return r, time.monotonic() - start

        for data in seeds:  # initial corpus, load order per seed_files()
            if spent():
                break
            r, elapsed = execute(data)
            if execs == 1 and r.outcome == "clean" and not r.edges:
                raise RuntimeError("no instrumentation detected: first execution hit zero edges")
            corpus.observe(data, r)  # raises on a crashing/hanging seed
            rec = rec or _Recorder(cfg.out_dir)
            rec.path_ids.add(coverage.path_id(r.edges))
            rec.tick(elapsed, execs, corpus)

        done = rec is None or spent()
        while not done:
            assert rec is not None
            seed = corpus.select()
            energy = assign_energy(seed, corpus)
            if energy < 1:
                raise ValueError(f"energy must be >= 1, got {energy} for seed {seed.id}")
            for _ in range(energy):
                if spent():
                    done = True
                    break
                cand = mutator.mutate(seed.data, rng, [s.data for s in corpus.seeds])
                r, elapsed = execute(cand)
                if r.outcome == "hang":
                    rec.hangs += 1
                    rec.hang_time_s += r.exec_time
                elif r.outcome == "crash":
                    rec.path_ids.add(coverage.path_id(r.edges))
                    rec.crash(cand, r, crash_site(r.stderr, source), elapsed, execs)
                else:
                    rec.path_ids.add(coverage.path_id(r.edges))
                    corpus.observe(cand, r)
                rec.tick(elapsed, execs, corpus)
            else:
                corpus.mark_fuzzed(seed)
                done = spent()
        if rec is not None:
            rec.tick(time.monotonic() - start, execs, corpus, final=True)
    finally:
        if rec is not None:
            rec.close()
        executor.close()
