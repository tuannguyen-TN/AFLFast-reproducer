"""Target execution harness. [implements FR-2 / ticket AFL-003]

Runs the instrumented target on one stdin input, enforces a timeout, and reports
an ExecResult. Outcome precedence: hang > crash (any terminating signal, AFL-018) > clean.
ASAN_OPTIONS is replaced, not appended (ADR-0002). No RNG, no schedule knowledge.
"""
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fuzzer.coverage import Hit, ShmBitmap

Outcome = Literal["clean", "crash", "hang"]
ASAN_OPTIONS = "abort_on_error=1:detect_leaks=0:symbolize=1"  # ADR-0002
DRAIN_TIMEOUT_S = 1.0  # AFL-028: bound on reading stderr after the timeout kill


@dataclass(frozen=True)
class ExecResult:
    exit_status: int | None  # None if killed by a signal or timed out
    signal: int | None  # terminating signal; None on timeout (our kill)
    timed_out: bool
    hits: frozenset[Hit]  # (edge, bucket) pairs (AFL-034); empty if timed_out
    exec_time: float  # wall-clock seconds
    stderr: bytes  # ASan report; consumed by dedup (AFL-013)

    @property
    def edges(self) -> frozenset[int]:
        """Distinct edge ids hit: the ADR-0005 s6 endpoint's unit, blind to hit counts."""
        return frozenset(e for e, _ in self.hits)

    @property
    def outcome(self) -> Outcome:
        if self.timed_out:
            return "hang"
        if self.signal is not None:  # AFL-018: timed_out handled above, so any signal is a crash
            return "crash"
        return "clean"

    @property
    def crashed(self) -> bool:
        return self.outcome == "crash"


class Executor:
    """Owns one ShmBitmap, reset before every run; call close() when done."""

    def __init__(self, target: Path, timeout_s: float = 1.0) -> None:
        self._target = str(Path(target).resolve())
        self._timeout_s = timeout_s
        self._bitmap = ShmBitmap()
        self._env = {**os.environ, "ASAN_OPTIONS": ASAN_OPTIONS, **self._bitmap.env()}

    def run(self, data: bytes) -> ExecResult:
        self._bitmap.reset()
        start = time.monotonic()
        with subprocess.Popen(
            [self._target], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, env=self._env,
        ) as p:
            try:
                _, err = p.communicate(data, timeout=self._timeout_s)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()  # reap first so the drain's TimeoutExpired can only come from the read loop
                try:
                    _, err = p.communicate(timeout=DRAIN_TIMEOUT_S)  # no input: already sent
                except subprocess.TimeoutExpired as e:
                    # ceiling: partial stderr if a descendant holds the pipe past DRAIN_TIMEOUT_S
                    err = e.stderr or b""  # cumulative across both communicate calls
                return ExecResult(None, None, True, frozenset(),
                                  time.monotonic() - start, err or b"")
            except BaseException:  # never leave the child running (parity with subprocess.run)
                p.kill()
                raise
        rc = p.returncode
        return ExecResult(
            exit_status=None if rc < 0 else rc,
            signal=-rc if rc < 0 else None,
            timed_out=False,
            hits=self._bitmap.hits(),
            exec_time=time.monotonic() - start,
            stderr=err or b"",
        )

    def close(self) -> None:
        """Release and unlink the bitmap. Idempotent (ShmBitmap.close is)."""
        self._bitmap.close()
