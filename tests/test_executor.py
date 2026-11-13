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


def _kill_pid_file(pid_file: Path) -> None:
    txt = pid_file.read_text().strip() if pid_file.exists() else ""
    if txt:
        try:
            os.kill(int(txt), signal.SIGKILL)
        except ProcessLookupError:
            pass


def _kill_tree(fifo: Path) -> None:
    """Kill the processes of ONE attempt: those whose argv ends with its FIFO path (the bg
    `sh -c` and the `cat` blocked in `open()`). The path carries a per-attempt uuid, is
    regex-escaped and anchored by `( |$)`, so a sibling `x10/...` is not matched by `x1`."""
    import re
    subprocess.run(["pkill", "-9", "-f", re.escape(str(fifo)) + "( |$)"], check=False)


def test_kill_tree_spares_prefixed_neighbour(tmp_path: Path) -> None:
    """AFL-028 review R2: cleaning `x1` must not kill a process running from `x10/...`."""
    neighbour = tmp_path / "x10" / "f"
    p = subprocess.Popen(["sh", "-c", "read x", "_", str(neighbour)], stdin=subprocess.PIPE)
    try:
        time.sleep(0.2)  # let sh exec its argv; pkill cannot match before that
        _kill_tree(tmp_path / "x1")
        time.sleep(0.2)
        assert p.poll() is None, "cleanup of x1 killed a process under x10"
        _kill_tree(neighbour)  # positive control: the exact path IS matched
        assert p.wait(timeout=5) == -signal.SIGKILL
    finally:
        p.kill()
        p.wait()
        if p.stdin:
            p.stdin.close()


def test_hang_stderr_written_after_kill_is_drained(tmp_path: Path) -> None:
    """AFL-028 AC3: a descendant writes stderr only after the kill (FIFO-tied), so a
    missing drain fails by causality, not by race. The bg list is forked before
    `exec 5>` so it does not inherit the FIFO write end. Each attempt has its own FIFO
    (`f-<uuid>`) and teardown kills that attempt's `sh -c`/`cat`, so a missed attempt
    leaves no stale reader to pair with the next attempt's writer (the 4/600 flake)."""
    import uuid
    mark = tmp_path / "m"
    for _ in range(20):
        fifo = tmp_path / f"f-{uuid.uuid4().hex}"
        os.mkfifo(fifo)
        body = (f'sh -c \'cat "$1" >/dev/null; echo late >&2\' _ "{fifo}" & '
                f'exec 5>"{fifo}"; : > "{mark}"; exec sleep 5')
        try:
            r = run_script(tmp_path, body, timeout_s=0.3)
        finally:
            _kill_tree(fifo)
        assert r.outcome == "hang"
        if mark.exists():
            break
    assert mark.exists(), "child never reached the marker in 20 attempts"
    assert r.stderr == b"late\n"


def test_hang_drain_bounded_when_descendant_holds_stderr(tmp_path: Path) -> None:
    """AFL-028 AC4: a background sleep holds stderr open; the run still returns."""
    from fuzzer.executor import DRAIN_TIMEOUT_S
    pid, mark = tmp_path / "p", tmp_path / "m"
    body = f'echo pre >&2; sleep 10 & echo $! > "{pid}"; : > "{mark}"; exec sleep 10'
    for _ in range(20):
        try:
            t = time.monotonic()
            r = run_script(tmp_path, body, timeout_s=0.3)
            elapsed = time.monotonic() - t
        finally:
            _kill_pid_file(pid)
        if mark.exists():
            break
    assert mark.exists(), "child never reached the marker in 20 attempts"
    # +1.0 s slack: cold /bin/sh fork/exec plus kill/reap under load (as in test_hang);
    # an unbounded drain blocks ~10 s, far beyond this.
    assert elapsed < 0.3 + DRAIN_TIMEOUT_S + 1.0
    assert r.outcome == "hang"
    assert r.stderr == b"pre\n"
