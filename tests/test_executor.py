"""AFL-003: Executor outcomes, timeout, ASan env (ADR-0002), bitmap reuse, cov_rt fail-loud."""
import os
import signal
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import needs_clang

from fuzzer.executor import ASAN_OPTIONS, Executor

TARGETS = Path(__file__).resolve().parent.parent / "targets"


def script(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "t.sh"
    p.write_text(f"#!/bin/sh\n{body}\n")
    p.chmod(0o755)
    return p


def run_script(tmp_path: Path, body: str, timeout_s: float = 1.0):  # type: ignore[no-untyped-def]
    ex = Executor(script(tmp_path, body), timeout_s)
    try:
        return ex.run(b"")
    finally:
        ex.close()


def test_clean_nonzero_exit(tmp_path: Path) -> None:
    r = run_script(tmp_path, "exit 3")
    assert (r.outcome, r.crashed, r.exit_status, r.signal) == ("clean", False, 3, None)
    assert not r.timed_out


@pytest.mark.parametrize("sig", [signal.SIGSEGV, signal.SIGABRT])
def test_crash_signals(tmp_path: Path, sig: signal.Signals) -> None:
    r = run_script(tmp_path, f"kill -{sig.name[3:]} $$")
    assert (r.outcome, r.crashed, r.signal, r.exit_status) == ("crash", True, sig, None)


def test_other_signal_is_not_crash(tmp_path: Path) -> None:
    assert run_script(tmp_path, "kill -TERM $$").outcome == "clean"


def test_hang(tmp_path: Path) -> None:
    t = time.monotonic()
    r = run_script(tmp_path, "exec sleep 5", timeout_s=0.3)
    assert time.monotonic() - t < 0.3 + 1
    assert (r.outcome, r.crashed, r.edges, r.timed_out) == ("hang", False, frozenset(), True)
    assert r.signal is None and r.exit_status is None


def test_env_forced_and_inherited(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASAN_OPTIONS", "abort_on_error=0:detect_leaks=1")
    monkeypatch.setenv("AFL003_KEEP", "yes")
    r = run_script(tmp_path, 'echo "$ASAN_OPTIONS|$AFL003_KEEP" >&2')
    assert r.stderr.strip() == f"{ASAN_OPTIONS}|yes".encode()


@pytest.fixture(scope="module")
def toy() -> Path:
    subprocess.run(["make", "-C", str(TARGETS), "bin/toy_parser"], check=True)
    return TARGETS / "bin" / "toy_parser"


@pytest.fixture
def ex(toy: Path) -> Iterator[Executor]:
    e = Executor(toy)
    yield e
    e.close()


@needs_clang
def test_asan_crash_despite_parent_env(ex: Executor, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASAN_OPTIONS", "abort_on_error=0:detect_leaks=1")
    r = ex.run(b"BUG")
    assert (r.outcome, r.signal) == ("crash", signal.SIGABRT)
    assert b"AddressSanitizer" in r.stderr


@needs_clang
def test_bitmap_reuse_no_stale_edges(ex: Executor, toy: Path) -> None:
    a, b, a2 = ex.run(b"A"), ex.run(b"B"), ex.run(b"A")
    assert a.edges and b.edges and a.edges != b.edges
    assert a2.edges == a.edges
    assert a.outcome == "clean" and a.exit_status == 0


def test_close_idempotent(tmp_path: Path) -> None:
    ex = Executor(script(tmp_path, "exit 0"))
    ex.close()
    ex.close()


@needs_clang
def test_cov_rt_fails_loudly_on_bad_shm(toy: Path) -> None:
    env = {**os.environ, "FUZZ_SHM_NAME": "afl003_no_such_segment"}
    p = subprocess.run([str(toy)], input=b"A", env=env, capture_output=True, check=False)
    assert p.returncode == 86  # positive: _exit, not a signal
    assert b"cov_rt" in p.stderr


@needs_clang
def test_cov_rt_failure_is_clean_via_executor(toy: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ex = Executor(toy)
    try:
        monkeypatch.setitem(ex._env, "FUZZ_SHM_NAME", "afl003_no_such_segment")
        r = ex.run(b"A")
    finally:
        ex.close()
    assert (r.outcome, r.exit_status) == ("clean", 86)


@pytest.mark.parametrize(("body", "want"), [("exec sleep 5", b""), ("echo hi >&2; exec sleep 5", b"hi\n")])
def test_hang_stderr_is_bytes(tmp_path: Path, body: str, want: bytes) -> None:
    r = run_script(tmp_path, body, timeout_s=0.3)  # nothing captured -> b"", never None
    assert r.outcome == "hang" and isinstance(r.stderr, bytes) and r.stderr == want


def test_close_after_run_raised_unlinks(tmp_path: Path) -> None:
    from multiprocessing import shared_memory
    target = script(tmp_path, "exit 0")
    ex = Executor(target)
    name = ex._env["FUZZ_SHM_NAME"]
    target.unlink()
    with pytest.raises(FileNotFoundError):
        ex.run(b"")
    ex.close()
    with pytest.raises(FileNotFoundError):
        shared_memory.SharedMemory(name=name)  # segment is gone
    ex.close()  # second close is a no-op
