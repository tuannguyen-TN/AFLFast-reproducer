"""Target execution harness. [implements FR-2 / ticket AFL-003]

Runs the instrumented target on one stdin input, enforces a timeout, and reports
an ExecResult. Outcome precedence: hang > crash (SIGSEGV/SIGABRT) > clean.
ASAN_OPTIONS is replaced, not appended (ADR-0002). No RNG, no schedule knowledge.
"""
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fuzzer.coverage import ShmBitmap

Outcome = Literal["clean", "crash", "hang"]
CRASH_SIGNALS = frozenset({signal.SIGSEGV, signal.SIGABRT})
ASAN_OPTIONS = "abort_on_error=1:detect_leaks=0:symbolize=1"  # ADR-0002


@dataclass(frozen=True)
class ExecResult:
    exit_status: int | None  # None if killed by a signal or timed out
    signal: int | None  # terminating signal; None on timeout (our kill)
    timed_out: bool
    edges: frozenset[int]  # empty if timed_out
    exec_time: float  # wall-clock seconds
    stderr: bytes  # ASan report; consumed by dedup (AFL-013)

    @property
    def outcome(self) -> Outcome:
        if self.timed_out:
            return "hang"
        if self.signal in CRASH_SIGNALS:
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
        try:
            p = subprocess.run(
                [self._target], input=data, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, timeout=self._timeout_s, env=self._env,
                check=False,  # non-zero exit / crash is a normal fuzz outcome
            )
        except subprocess.TimeoutExpired as e:
            return ExecResult(None, None, True, frozenset(), time.monotonic() - start,
                              e.stderr or b"")
        rc = p.returncode
        return ExecResult(
            exit_status=None if rc < 0 else rc,
            signal=-rc if rc < 0 else None,
            timed_out=False,
            edges=self._bitmap.edges(),
            exec_time=time.monotonic() - start,
            stderr=p.stderr or b"",
        )

    def close(self) -> None:
        """Release and unlink the bitmap. Idempotent (ShmBitmap.close is)."""
        self._bitmap.close()
