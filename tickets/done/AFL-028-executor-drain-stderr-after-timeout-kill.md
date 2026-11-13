---
id: AFL-028
title: Drain stderr after the timeout kill so a timed-out run's stderr is complete
requirement: NFR-1 (reproducibility), FR-2 (execute a target safely)
paper_ref: n/a (executor correctness; Python `subprocess` docs, `Popen.communicate` kill-then-communicate pattern)
module: src/fuzzer/executor.py, tests/test_executor.py
depends_on: [AFL-003]
status: done
owner: developer
---

## Goal
A timed-out run's stderr is complete. Today `Executor.run` calls
`subprocess.run(..., stderr=PIPE, timeout=...)` and on `TimeoutExpired` returns
`e.stderr or b""`. On POSIX, CPython 3.12's `Popen._communicate` checks the
timeout after `select()` returns but before it reads the ready fds, and `run()`
then only does `kill()` + `wait()` and never reads the pipe again. Bytes the child
wrote before the kill are dropped non-deterministically. The AFL-027 reviewer
reproduced this with the unmodified executor: about 1 in 400 runs under 10-core
load, and 2-3 in 100 with no load and the write placed near the deadline. The fix
follows the documented Python pattern: `Popen`, then `communicate(timeout=…)`; on
`TimeoutExpired`, `kill()`, then `communicate()` again to drain. The second call
has its own short bound, in case a grandchild holds the pipe open.

**Schedule:** must land before the AFL-011 freeze. It is not needed for M1 and is
not scheduled ahead of it: it runs in parallel with AFL-007. AFL-007 does not
depend on it, because the executor interface (`Executor`, `ExecResult`) does not
change. AFL-027 depends on it.

## Acceptance criteria
- [ ] **AC1, scope / unchanged behaviour.** The only behaviour change is that a
      timed-out run's stderr is complete. These stay exactly as they are:
      outcome classification (hang > crash > clean); edges discarded on timeout
      (`edges == frozenset()`); `exec_time` semantics (wall-clock seconds for the
      run, as in AFL-003); every other `ExecResult` field (`exit_status is None`,
      `signal is None`, `timed_out is True` on timeout; clean and crash results
      field-for-field as today). The `Executor` / `ExecResult` interface is
      unchanged. AFL-003's existing tests in `tests/test_executor.py` pass and are
      not edited by this ticket (this ticket only adds tests).
- [ ] **AC2, bounded cost.** The drain bound only lengthens a timed-out run by a
      bounded amount (at most the drain bound), and has no effect on clean or crash
      runs (the drain code path is entered only on `TimeoutExpired`).
- [ ] **AC3, test of the fix.** A deterministic test where the child (or a
      descendant) writes stderr near or after the deadline, and `r.stderr` still
      holds the complete bytes written. "Deterministic" means both: (i) with the
      fixed executor it passes 200 out of 200 under N-physical-core CPU load
      (the AFL-027 AC4 load recipe, N = `sysctl -n hw.physicalcpu`), and (ii) with
      the drain removed (mutant M-nodrain, AC5) it fails on every run, not at the
      ~1/400 race rate. The exact command and result are recorded in the Log.
      **Coordinate, do not duplicate:** AFL-027's `test_hang_stderr_captured_bytes`
      (marker proves the write happened before the kill) is the natural witness for
      the write-before-kill case, but it belongs to AFL-027 and is not committed
      before this ticket lands. Do not add a second copy of that case. This
      ticket's test covers a case whose failure under M-nodrain is deterministic;
      AFL-027's test is re-run against this fix under AFL-027 AC3/AC4.
- [ ] **AC4, grandchild holds the pipe.** A test where the target leaves a
      descendant holding stderr open past the deadline (for example, a script that
      backgrounds a long `sleep` inheriting stderr, then `exec sleep` itself): the
      run still returns within timeout + drain bound + slack, measured wall-clock
      and asserted. The slack value and its reason are in a comment next to it. The
      background process is killed in test cleanup and does not outlive the test.
- [ ] **AC5, mutants.** Each mutant below, applied to a throwaway copy of `src/`
      outside the repo, makes at least one test fail; the unmodified fixed executor
      passes. Run with `pytest -o pythonpath=<copy>/src` (the repo's pyproject
      `pythonpath=["src"]` shadows `PYTHONPATH`), verify in-process that
      `sys.modules["fuzzer.executor"].__file__` resolves to the copy, and delete
      the copy afterwards (as in AFL-023 AC4 / AFL-027 AC3):
      - **M-nodrain:** the drain removed, back to current behaviour (kill + wait,
        return the first `TimeoutExpired`'s stderr). Must fail the AC3 test.
      - **M-unbounded:** the drain without a bound (second `communicate()` with no
        timeout). Must fail the AC4 test.
      The developer records each mutant and the failing test id in the Log; the
      reviewer re-runs them.
- [ ] **AC6, gates.** The diff under `src/`, `tests/`, `harness/`, `targets/` and
      `docs/` attributable to this ticket changes only `src/fuzzer/executor.py`
      and `tests/test_executor.py` (ticket and board files excepted).
      `ruff check . && mypy src && pytest` pass.

## Technical notes (architect)
- **Shape of `run()` (decided).** This replaces `subprocess.run` with the body that
  `run()` already has, adding a bounded drain. Order: **kill, then reap, then drain.**
  ```python
  with subprocess.Popen([self._target], stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                        env=self._env) as p:
      try:
          _, err = p.communicate(data, timeout=self._timeout_s)
      except subprocess.TimeoutExpired:
          p.kill()
          p.wait()  # reap first (as run() does today): the drain's TimeoutExpired
                    # can then only come from the read loop, which carries stderr
          try:
              _, err = p.communicate(timeout=DRAIN_TIMEOUT_S)  # NO input (see below)
          except subprocess.TimeoutExpired as e:
              err = e.stderr  # cumulative, see Q2
          return ExecResult(None, None, True, frozenset(),
                            time.monotonic() - start, err or b"")
      except BaseException:  # parity with subprocess.run: never leave the child running
          p.kill()
          raise
  # clean/crash: rc = p.returncode, edges, exec_time, stderr=err or b"" exactly as today
  ```
  Points the reviewer should check:
  - `stdin=PIPE` always, as `run(input=...)` does even for `b""`, so the target sees
    the same stdin as today. `stdout=DEVNULL` is unchanged; AFL-018's SIGPIPE AC
    relies on it.
  - The second `communicate()` gets **no input**. Passing `data` again raises
    `ValueError` ("Cannot send input after starting communication"), but only for
    non-empty `data`, so the `b""` tests would not catch the mistake.
  - Why reap before draining: if the drain is left to call `wait()` itself, `wait()`
    can raise its own `TimeoutExpired`, and that one has `stderr=None`. Reaping first
    removes that source. The `p.wait()` after a SIGKILL is the same wait that
    `run()` already does today, so it is not new cost.
  - `except BaseException: p.kill(); raise` keeps `run()`'s existing behaviour.
    Without it, `Popen.__exit__` would `wait()` with no bound on a live child after
    an unexpected exception.
  - Reaping the direct child before the drain does not lose bytes: data already in
    the pipe outlives the writer.
  - No process-group kill (`start_new_session`/`killpg`). It would be a behaviour
    change beyond AC1. It would also hide M-unbounded, because it would kill the
    AC4 grandchild and close the pipe.
- **Q1, drain bound: a module constant `DRAIN_TIMEOUT_S = 1.0`, not derived from
  `timeout_s`.** It sits next to `ASAN_OPTIONS`. It is not a constructor argument,
  because AC1 freezes the interface. Reasons:
  - Once the direct child is reaped, its bytes are already in the pipe and EOF is
    immediate, so a normal hang drains in microseconds. The bound only does
    anything when a descendant holds stderr. The one realistic descendant here is
    ASan's symbolizer (sanitizer_common starts it with inherited fd 2) when a
    crash's symbolization runs past the deadline. It exits on stdin EOF once the
    target is dead.
  - The drain therefore waits on scheduler latency for pipe teardown, not on the
    target's compute time. Scaling it with `timeout_s` would make hangs cost more for
    no reason.
  - 1.0 s is about 100x the macOS scheduling quantum (~10 ms), so it covers the
    CPython 3.12 check-after-`select()` quirk inside the drain (loss needs a parent
    stall of 1 s or more). It costs nothing in the normal case.
  - The value is code, so the commit hash records it (NFR-1). No `run.json` field
    is needed.
- **Q2, drain bound exceeded.**
  - **stderr:** return `e.stderr or b""` from the **second** `TimeoutExpired`.
    `communicate` keeps one per-`Popen` output buffer across calls once
    `_communication_started` is set (Python docs: "retrying communication will not
    lose any output"). So `e2.stderr` holds everything read in both calls, a superset
    of the first call's bytes. The first `TimeoutExpired` is never used.
  - **Cleanup:** the child is already reaped by `p.wait()`, so no zombie is left.
    `Popen.__exit__` closes `p.stdin`/`p.stderr`, whether or not `communicate`'s
    selector unregistered them, and its trailing `wait()` returns at once. So no fd
    is left open. A surviving grandchild is not ours to kill (see process-group
    point above). It gets EPIPE on its next write and is reaped by init.
  - **Logged/counted:** neither. The executor has no logger, a counter would need a
    new `ExecResult` field (forbidden by AC1), and hang stderr is in no metric.
    Outcome stays `"hang"`. Put a one-line code comment on the `except` naming the
    known ceiling: partial stderr if a descendant holds the pipe for longer than
    `DRAIN_TIMEOUT_S`.
- **Q3, `exec_time` stops after the drain, immediately before `ExecResult` is
  built.**
  - This is where it stops today: after `run()`'s kill and wait.
  - It is the full wall cost of the run, like the clean/crash path, which includes
    reading to EOF and the reap.
  - Nothing downstream reads hang `exec_time`:
    - `Corpus.observe()` rejects non-clean results, so `Seed.exec_time` only ever
      comes from clean runs (ADR-0004 §7).
    - The schedules do not read `exec_time` (ADR-0004 amendment, AFL-006).
    - AFL-007 counts hangs in `hangs` only, and `metrics.csv` has no per-exec time.
    - The AFL-011 timing probe uses final `execs` / `elapsed_s`, which is trial
      wall clock and includes the drain wherever this clock stops.
    - AFL-012 does not read `exec_time`.

    So metrics are unchanged under either reading. "After" keeps AFL-003's
    semantics.
- **Q4, AC3 test construction (`test_hang_stderr_written_after_kill_is_drained`).**
  - **Mechanism:** a descendant writes **only after the direct child has died**,
    with the timing tied to the death through a FIFO. Under M-nodrain the parent
    has stopped reading by then, so the test fails by causality, not by race.
  - **Body** (`F` is `os.mkfifo(tmp_path / "f")`, made by the test; `P` is a pid
    file; `M` is a marker; `timeout_s=0.3`):
    `{ cat "$F" >/dev/null; echo late >&2; } & echo $! > "$P"; exec 5>"$F"; : > "$M"; exec sleep 5`
  - **The background list must be forked before `exec 5>"$F"`.** Otherwise it
    inherits the FIFO write end and `cat` never sees EOF.
  - **Why it is causal:** `exec 5>"$F"` blocks until `cat` opens the FIFO.
    `sleep` (the direct child, same pid) inherits fd 5. The executor's SIGKILL
    closes fd 5, then `cat` gets EOF, then `echo late` runs, then the subshell
    exits. That last exit is the final writer going away, so the pipe reaches EOF.
    So `late\n` reaches the pipe strictly after `kill()`, which is strictly after the
    first `communicate` raised. M-nodrain (kill + wait + first stderr) never reads
    again, so it gets `b""` on every run where `M` exists.
  - **Proof and retry:** this is the AFL-027 pattern. `M` proves the rendezvous
    happened before the kill. Retry `run()` up to 20 times until `M` exists, then
    `assert M.exists()`, then `assert r.stderr == b"late\n"` (exact). If `M` is
    absent 20 times, the test also fails, so M-nodrain fails on every run.
  - **Pass does not depend on load:** with the fix, the pass needs only the
    post-kill chain (`cat` wakes and exits, `echo`, subshell exits) and the
    parent's wake from `select` to finish within `DRAIN_TIMEOUT_S`. That is a few
    context switches (milliseconds) against 1.0 s, about 100x margin under N-core
    load. Any bounded drain has some margin like this. Removing it entirely would
    need an unbounded drain, which M-unbounded/AC4 forbid. AC3(i)'s 200/200 stress
    run is the empirical check.
  - **Not a copy of AFL-027's case:** the shell writes nothing before the kill.
  - **Cleanup:** in `finally`, for each attempt, SIGKILL the pid in `P` if it is
    non-empty, ignoring `ProcessLookupError`. On a passing run that pid has already
    exited.
- **AC4 test (`test_hang_drain_bounded_when_descendant_holds_stderr`).**
  - **Body:** `echo pre >&2; sleep 10 & echo $! > "$P"; : > "$M"; exec sleep 10`
    with `timeout_s=0.3`. The background `sleep` gets `/dev/null` as stdin
    (non-interactive sh) and holds only stderr.
  - **Retry:** as in AC3, until `M` exists, with the attempt count asserted.
  - **Assertions on the attempt with `M`:**
    - measured wall-clock `< 0.3 + DRAIN_TIMEOUT_S + 1.0`;
    - `outcome == "hang"`;
    - `r.stderr == b"pre\n"`. This pins Q2: on a drain-bound timeout the
      cumulative stderr is returned, not `b""`. It is the drain-exceeded path, not
      AFL-027's case.
  - **Slack comment:** 1.0 s covers cold `/bin/sh` fork/exec plus kill/reap under
    N-core load. It is the same `+1` s convention as `test_hang`. M-unbounded
    blocks for the full `sleep 10` (about 10.3 s), so the gap of about 7.7 s cannot
    be hidden by the slack.
  - **Cleanup:** SIGKILL the pid from `P` in `finally` for every attempt. The tester
    checks with `pgrep sleep`.
  - **Importing the constant:** import `DRAIN_TIMEOUT_S` **inside the test
    function**, as `test_close_after_run_raised_unlinks` does for `shared_memory`.
    This leaves the top-of-file import line untouched; see Test placement.
- **AC2 reading.** "Lengthens by at most the drain bound" is measured against
  today. The kill and reap already exist in `run()`. The new cost is the drain
  `communicate`, which is at most `DRAIN_TIMEOUT_S`. The drain is reached only from
  the `except TimeoutExpired` branch, so clean and crash runs go through the same
  single `communicate` as before.
- **Test placement (decided).** Append both new tests at the **end** of
  `tests/test_executor.py`, after `test_close_after_run_raised_unlinks`.
  - AFL-027's uncommitted hunk covers the two hang-stderr tests (about lines
    117-136). An append after line 150 leaves more than 6 unchanged lines between
    the hunks, so `git diff` produces separate hunks. The orchestrator can then
    stage AFL-028's hunk alone with a filtered patch and `git apply --cached`.
  - With the in-function import, AFL-028 adds exactly one hunk to this file.
  - Helpers `script()`/`run_script()` are reused, with no new fixtures.
  - A separate `tests/test_executor_drain.py` would make staging trivial (a
    whole-file add), but it would need an AC6 wording change and would duplicate the
    helpers. It is **not recommended**.
- **Replay and metrics are unaffected.** Hangs are already the one disclosed
  timing-dependent exception to exec-index replay (ADR-0005, AFL-007, AFL-011), and
  hang stderr is in no metric or replay column. Crash stderr, which dedup (AFL-013)
  uses, does not go through the timeout path.
- **Out of scope:** the clean/crash path (`communicate` already reads to EOF
  there). A target that exits while a descendant holds stderr would run into the
  overall timeout on that path today; our targets do not fork, and this ticket does
  not change it.
- **Conflict with AFL-018.** AFL-018 also edits `src/fuzzer/executor.py` and
  `tests/test_executor.py`. They must not be worked concurrently; whichever lands
  second rebases onto the first. AFL-018 keeps "our own timeout kill" out of the
  crash class, so the timeout path's `signal is None` (AC1) holds under both.
- **Separately findable.** Executor changes before the freeze must be separately
  findable and reviewable (human decision, 2026-11-12). The working tree already
  holds AFL-027's uncommitted `tests/test_executor.py` diff, which stays uncommitted
  until this ticket lands. This ticket's commit must contain only AFL-028 hunks;
  the human stages them separately from AFL-027's.

**Known limitation (human decision, 2026-11-13).** The executor kills only its direct child, not grandchildren. This is accepted for the campaign because the targets never fork. Tests that spawn grandchildren (`sh -c ... cat`) must kill them on teardown (`_kill_tree` / `_kill_pid_file` in tests/test_executor.py). `src/fuzzer/executor.py` is deliberately unchanged for this.

## Test approach (tester)
Run the gates in a clean clone. Re-run the AC3 stress loop (200/200 under
N-physical-core load) and confirm the Log command reproduces it. Re-apply
M-nodrain and M-unbounded to a throwaway copy outside the repo (module path
verified, `-o pythonpath=<copy>/src`) and confirm each fails its test. Confirm
AFL-003's existing executor tests are unedited and pass, that only
`src/fuzzer/executor.py` and `tests/test_executor.py` changed, and that no
background process from AC4 survives the test run (`pgrep sleep` before/after).

## Log
- 2026-11-12 — created (req-engineer) from AFL-027 review finding (cause 2
  reproduced: hang stderr undrained after kill, ~1/400 under load) (human decision)
- 2026-11-12 — technical notes (architect): open questions resolved (Q1
  `DRAIN_TIMEOUT_S = 1.0` constant; Q2 second `TimeoutExpired`'s cumulative stderr,
  reap-before-drain, `with Popen` cleanup, not logged/counted; Q3 `exec_time` stops
  after the drain as today; Q4 FIFO-tied post-kill write, causal under M-nodrain);
  AC4 construction; tests appended at end of tests/test_executor.py; no AC unworkable
- 2026-11-12 — implemented (developer). executor.py: `subprocess.run` replaced by `Popen` + `communicate(timeout)`; on `TimeoutExpired` kill, `wait()`, bounded `communicate(timeout=DRAIN_TIMEOUT_S)` (no input), `e.stderr` on drain timeout; `except BaseException: kill; raise`; `DRAIN_TIMEOUT_S = 1.0`. Tests appended at end of tests/test_executor.py: `test_hang_stderr_written_after_kill_is_drained` (AC3), `test_hang_drain_bounded_when_descendant_holds_stderr` (AC4).
- 2026-11-12 — AC5 mutants on a throwaway copy of src (deleted after), `pytest -o pythonpath=<copy>/src --no-cov`, `sys.modules["fuzzer.executor"].__file__` printed from inside the run and resolved to the copy: M-nodrain (kill+wait, return first TimeoutExpired's stderr) fails `tests/test_executor.py::test_hang_stderr_written_after_kill_is_drained`; M-unbounded (`communicate()` without timeout) fails `tests/test_executor.py::test_hang_drain_bounded_when_descendant_holds_stderr`. Real executor passes both.
- 2026-11-12 — AC3 stress: N=`sysctl -n hw.physicalcpu`=10; `for i in $(seq 10); do (yes >/dev/null &); done`; 200x `.venv/bin/python -m pytest --no-cov -q -p no:cacheprovider tests/test_executor.py -k "written_after_kill or drain_bounded"` -> 200/200 pass; same loop, `-k hang_stderr_captured_bytes` (AFL-027) -> 200/200 pass. Then `pkill -x yes`: `pgrep -x yes` empty, no `cat` left.
- 2026-11-12 — review: APPROVE -> testing. AC1-AC6 verified (see Review); ruff/mypy green, tests/test_executor.py 16/16; M-nodrain and M-unbounded re-run on a /tmp copy (module path verified, copy deleted), each fails its target test. Full-suite pytest and the 200/200 stress on the final code are left to the tester (reviewer)
- 2026-11-12 — tester: gates on the final code (with AFL-007's concurrent fuzzer.py/test_fuzzer.py in the tree): `.venv/bin/ruff check .` -> `All checks passed!`; `.venv/bin/mypy src` -> `Success: no issues found in 8 source files`; `.venv/bin/python -m pytest` -> `127 passed, 2 deselected in 8.52s` (executor.py 95% cov). No failures to attribute.
- 2026-11-12 — tester: AC3 stress on the final code. N=`sysctl -n hw.physicalcpu`=10, `for i in $(seq 10); do (yes >/dev/null &); done` (10 `yes` confirmed before and after each loop). 200x `.venv/bin/python -m pytest --no-cov -q -p no:cacheprovider tests/test_executor.py -k "written_after_kill or drain_bounded"` -> 200 pass / 0 fail (6m11s). Same loop with `-k hang_stderr_captured_bytes` (AFL-027, informational) -> 200 pass / 0 fail. `pkill -x yes`; `pgrep -x yes` empty. Leftover `cat`/`sleep` right after and again after 15 s: only the pre-existing `sleep 60` with ppid 93726; no `cat`, no `sleep 10`.
- 2026-11-12 — tester: AC5 mutants on the final code, copies of src/ under /Users/shinobi07/.claude/jobs/57707320/tmp/afl028t/{nodrain,unbounded} (deleted after). Module path proven in-process by a `-p afl028probe` plugin printing `sys.modules["fuzzer.executor"].__file__` at session finish. Command: `PYTHONPATH=<tmp> .venv/bin/python -m pytest -p afl028probe -p no:cacheprovider -o pythonpath=<copy>/src --no-cov tests/test_executor.py`.
  - M-nodrain (kill, wait, `err = e0.stderr or b""` from the first TimeoutExpired; drain removed): probe -> `.../afl028t/nodrain/src/fuzzer/executor.py`; FAILED `tests/test_executor.py::test_hang_stderr_written_after_kill_is_drained` (`assert b'' == b'late\n'`); the other 15 pass.
  - M-unbounded (`p.communicate()` with no timeout): probe -> `.../afl028t/unbounded/src/fuzzer/executor.py`; FAILED `tests/test_executor.py::test_hang_drain_bounded_when_descendant_holds_stderr` (`assert 10.166549417190254 < ((0.3 + 1.0) + 1.0)`); the other 15 pass.
  - Unmodified: probe -> repo `src/fuzzer/executor.py`; 16/16 pass.
- 2026-11-12 — tester: boundary check (human-requested). Three cases, each `r.stderr == pre + post` exactly, where PRE is written before the deadline (marker written after it) and POST only after the SIGKILL (FIFO-blocked bg writer); `communicate` is wrapped so the first TimeoutExpired's stderr (bytes read before the deadline) is recorded and must be a prefix of the final stderr. Cases: small (22 B pre + 17 B post); multichunk_pre (100 000 B period-251 pattern + 17 B post marker); multichunk_pre_and_post (100 000 B pre + 100 000 B post, so the drain itself needs several reads). Results: idle 50/50 exact in each case; under 10-`yes` load 50/50 exact in each case; the first communicate had read >0 bytes in 50/50 of every case, both runs; 0 marker retries. Negative control: the same check against the M-nodrain copy -> 0/5 exact in each case (so the check is not vacuous). Source (deleted after):
    ```python
    """AFL-028 boundary check (throwaway): stderr == pre-deadline bytes + post-kill bytes, exactly.

    usage: python boundary_check.py <repo> <iterations>
    Each case: the shell writes PRE (before the deadline, proven by marker M written after it),
    then a bg writer blocked on a FIFO writes POST only after the direct child is SIGKILLed.
    communicate() is wrapped to record the first TimeoutExpired's stderr (bytes read before the
    deadline); it must be a non-strict prefix of the final stderr.
    """
    import os
    import signal
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    repo = Path(sys.argv[1])
    iters = int(sys.argv[2])
    sys.path.insert(0, str(repo / "src"))
    from fuzzer.executor import Executor  # noqa: E402

    first_err: list[bytes | None] = []
    _orig = subprocess.Popen.communicate


    def _wrapped(self, input=None, timeout=None):  # type: ignore[no-untyped-def]
        try:
            return _orig(self, input, timeout)
        except subprocess.TimeoutExpired as e:
            first_err.append(e.stderr or b"")
            raise


    subprocess.Popen.communicate = _wrapped  # type: ignore[method-assign]

    PATTERN = bytes(i % 251 for i in range(100_000))  # period 251: a shift/dup/drop is visible
    BIG_POST = bytes((i * 7) % 253 for i in range(100_000))
    CASES = {
        "small": (b"PRE-MARKER-0123456789\n", b"POST-KILL-MARKER\n"),
        "multichunk_pre": (PATTERN, b"POST-KILL-MARKER\n"),
        "multichunk_pre_and_post": (PATTERN, BIG_POST),
    }
    TMP = Path(__file__).resolve().parent


    def release_fifo(fifo: Path) -> None:
        try:  # unblock a cat still waiting in open() so nothing leaks
            fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
            os.close(fd)
        except OSError:
            pass


    def kill_pid(p: Path) -> None:
        txt = p.read_text().strip() if p.exists() else ""
        if txt:
            try:
                os.kill(int(txt), signal.SIGKILL)
            except ProcessLookupError:
                pass


    def one(name: str, pre: bytes, post: bytes) -> tuple[bool, int, int]:
        with tempfile.TemporaryDirectory(dir=TMP) as d:
            d_ = Path(d)
            fifo, pid, mark = d_ / "f", d_ / "p", d_ / "m"
            (d_ / "pre").write_bytes(pre)
            (d_ / "post").write_bytes(post)
            os.mkfifo(fifo)
            body = (f'{{ cat "{fifo}" >/dev/null; cat "{d_}/post" >&2; }} & echo $! > "{pid}"; '
                    f'exec 5>"{fifo}"; cat "{d_}/pre" >&2; : > "{mark}"; exec sleep 5')
            tgt = d_ / "t.sh"
            tgt.write_text(f"#!/bin/sh\n{body}\n")
            tgt.chmod(0o755)
            for attempt in range(1, 21):
                first_err.clear()
                pid.write_text("")
                ex = Executor(tgt, 0.3)
                try:
                    r = ex.run(b"")
                finally:
                    ex.close()
                    kill_pid(pid)
                    release_fifo(fifo)
                if mark.exists():
                    break
            else:
                print(f"{name}: marker never written in 20 attempts")
                return False, attempt, -1
            fe = first_err[0] if first_err else None
            ok = (r.outcome == "hang" and r.stderr == pre + post
                  and fe is not None and r.stderr.startswith(fe))
            if not ok:
                print(f"{name}: FAIL len={len(r.stderr)} want={len(pre + post)} "
                      f"first_err_len={None if fe is None else len(fe)}")
            return ok, attempt, (len(fe) if fe is not None else -1)


    passes = {k: 0 for k in CASES}
    pre_read_nonempty = {k: 0 for k in CASES}
    retries = 0
    for _ in range(iters):
        for k, (pre, post) in CASES.items():
            ok, att, fel = one(k, pre, post)
            passes[k] += ok
            pre_read_nonempty[k] += fel > 0
            retries += att - 1
    for k in CASES:
        print(f"{k}: {passes[k]}/{iters} exact; first-communicate read >0 bytes in "
              f"{pre_read_nonempty[k]}/{iters}")
    print(f"extra attempts (marker retry): {retries}")
    sys.exit(0 if all(v == iters for v in passes.values()) else 1)
    ```
- 2026-11-12 — tester: experimental validity. `fuzzer.run` builds one `Executor` and one `execute()` used by both arms; `cfg.schedule` is read only at `SCHEDULES[cfg.schedule]` (fuzzer.py:148), so the drain applies to uniform and fast identically. The hang branch (fuzzer.py:193-195) reads only `outcome` and `exec_time`, never `stderr` or `edges` (matches ADR-0005 §5). Exec-indexed replay is unaffected: the drain changes no exec-indexed value. Its only effect is time: up to `DRAIN_TIMEOUT_S` = 1 s extra per hang, which only happens when a descendant holds stderr. That can shift `elapsed_s`, `hang_time_s` and how many execs fit into `cfg.seconds`, and both are already outside the replay guarantee (ADR-0005). Acceptable; the AFL-011 timing probe reports how often it happens. Non-blocking doc staleness: Technical notes Q3 says "metrics.csv has no per-exec time", but AFL-007 now writes `hang_time_s` (sum of hang `exec_time`, including the drain). ADR-0005 already records this, so nothing needs to change in AFL-028's code.
- 2026-11-12 — tester: PASS, ready for crew-lead DoD
- 2026-11-12 — crew-lead: DoD PASS -> done. AC1–AC6 verified against the Log/Review and the live diff (AFL-028 hunks confined to src/fuzzer/executor.py and the appended tests/test_executor.py hunk; the l.114 removal is AFL-027's). Gates re-run on the current tree: `.venv/bin/ruff check .` -> All checks passed!; `.venv/bin/mypy src` -> Success: no issues found in 8 source files; `.venv/bin/python -m pytest -q` -> exit 0, 163 passed (count includes concurrent AFL-007/AFL-029 tests). Stress 200/200 under 10-core load, M-nodrain and M-unbounded each caught, boundary check 50/50 exact idle and loaded with 0/5 negative control (tester). Gate hook passed on the move. Not yet committed; commit must contain only AFL-028 hunks.
- Note (crew-lead, 2026-11-12): Technical notes Q3 ('metrics.csv has no per-exec time') and the statement that AFL-007 counts hangs only in `hangs` are superseded. AFL-007 now writes `hang_time_s`, the cumulative hang `exec_time` including the kill/reap/drain, per ADR-0005 §4–§5. No code change follows from this.
- 2026-11-12 — Record (moved from INDEX 'Suggested next pull'): until AFL-028 landed, a ~1/400 failure of `test_hang_stderr_captured_bytes` in the done gate was attributed to AFL-028 and not re-run until green (human decision, 2026-11-12). Lapsed now that AFL-028 is done (req-engineer)
- 2026-11-13 — developer: reopened for the AFL-027 stress flake (`test_hang_stderr_written_after_kill_is_drained` failed 4/600 with `b'' == b'late\n'`, 4 orphan `cat` on the FIFO). Cause CONFIRMED as a test race, not the 1.0 s drain bound: forcing one missed attempt (killed after forking the bg list, before `exec 5>`) and then running the normal attempt reproduces it deterministically, with the marker reached and `r.stderr == b''`, and leaves an orphan `cat <fifo>`. The control without the forced miss gives `b'late\n'` and no orphan. A stale reader from the missed attempt pairs with the next `exec 5>`, gets EOF and exits silently, so the new `cat` never sees a writer and `late` is never written. The drain gives up on a write that never happens, so the stop condition (drain bound too short) did not apply and the executor is untouched.
- 2026-11-13 — developer: fix, test-only (tests/test_executor.py, AFL-028 region). Each attempt gets its own FIFO (`f{i}`). Teardown calls `_kill_tree(tmp_path)`, which runs `pkill -9 -f <tmp_path>` and kills the t.sh shell, the bg subshell and any `cat` blocked in `open()`, whichever point the attempt was killed at. The pid file is gone from this test. All assertions are unchanged. `test_hang_drain_bounded_when_descendant_holds_stderr` is unchanged: its `sleep 10` is killed by `_kill_pid_file`, and the stress run left none behind (a kill before `echo $!` could strand one for at most 10 s).
- 2026-11-13 — developer: stress with 10 `yes` (PIDs recorded and killed afterwards, 0 left), 2 concurrent x 300 iterations of both tests: 600/600 runs exit 0, so 1200 test executions pass. Load average was 2.4 at the start, rising to about 16 with other agents. Orphans: no `cat` or test process left; `pgrep -fl` right after the run printed 4, but they were the driver's own shell subshells carrying the pattern in their argv, and the pattern with a `[x]` guard then gave 0. This 4 is inferred rather than listed, because the processes were gone by the time I looked.
- 2026-11-13 — developer: mutant (second `communicate` removed, first `TimeoutExpired`'s stderr returned) in a throwaway copy under the job tmp dir, `fuzzer.executor.__file__` confirmed to resolve to the copy: `test_hang_stderr_written_after_kill_is_drained` FAILS (`b'' == b'late\n'`), as required. Scratch deleted. Gates without load (load 7): ruff clean, mypy clean, 205 passed, 2 deselected.
- 2026-11-13 — review (reviewer): CHANGES REQUESTED, review -> in-progress (review bounce 1 of this reopen). Causal claim confirmed independently; fix direction (per-attempt FIFO) correct; executor untouched and its 1.0 s drain bound is not implicated. REQUIRED (human decision, 2026-11-13): R1 `_kill_tree` must not match a prefixed neighbour directory; R2 a test that a process under a neighbouring prefixed directory survives cleanup; R3 orphan check recorded per protocol. Gates green: ruff clean, mypy clean, pytest 211 passed, 2 deselected. See Review (reviewer, 2026-11-13)
- 2026-11-13 — developer: review bounce fixes R1-R3 (tests/test_executor.py, AFL-028 region only; lines 1-150 byte-identical, src/ untouched). R1: each attempt's FIFO is `f-<uuid4().hex>`; the bg list is now `sh -c 'cat "$1" >/dev/null; echo late >&2' _ <fifo> &`, so BOTH the bg `sh` and its `cat` carry the FIFO path in argv. The t.sh shell has no token, but the executor kills it itself. `_kill_tree(fifo)` runs `pkill -9 -f` with `re.escape(str(fifo)) + "( |$)"`: unique per attempt, escaped, and anchored at the end of argv, so no sibling directory or other attempt can match. I used the uuid path rather than the trailing-`/` fallback because the old `{ ...; }` subshell carries no token. AC3 assertions are unchanged.
- 2026-11-13 — developer: R2: `test_kill_tree_spares_prefixed_neighbour` starts `sh -c 'read x' _ <tmp>/x10/f`, runs `_kill_tree(<tmp>/x1)`, asserts the process is alive, then positive-controls that `_kill_tree` of the exact path kills it (-SIGKILL), and kills it by PID in `finally`. Mutant in a scratch copy (anchor `( |$)` removed, so the pattern is the unanchored path): it FAILS (`poll()` returned -9: x1 cleanup killed the x10 process), and `test_hang_stderr_written_after_kill_is_drained` still passes there. On the fix it passes. Scratch deleted.
- 2026-11-13 — developer: R3 orphan check: 50 runs of `.venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_executor.py -k "written_after_kill or drain_bounded or neighbour"`, 50/50 passed (load about 3). Then, in a separate Bash call after a 6 s polling wait, with no result for any pattern (rc=1): `pgrep -fl '[p]ytest-of-shinobi07/pytest-[0-9]+/test_hang_(stderr_written_after|drain_bounded_when_d)'`; `pgrep -xl cat`; `pgrep -fl '[f]-[0-9a-f]{32}'` (the uuid FIFO token); `pgrep -fl '[t]est_kill_tree_spares'`. No 600-run stress repeated. Gates (load 2.7): ruff clean, mypy clean, pytest 212 passed, 2 deselected.
- 2026-11-13 — re-review (reviewer): APPROVE -> testing. R1-R3 verified; M-nodrain re-run against the rewritten `sh -c` body fails 10/10 with `b'' == b'late\n'` and the marker reached; the R2 anchor-removed mutant fails; orphan check clean; src/ and AFL-027 hunk unchanged. Gates: ruff clean, mypy clean, pytest 212 passed, 2 deselected. One non-blocking residual (pre-exec fork window) with a tested one-line hardening, for the human to take or leave. See Review (reviewer, 2026-11-13, re-review)
- 2026-11-13 — tester: PASS on the reopen; stays in testing/, ready for crew-lead DoD. Clean copy (rsync, no .venv/results/.git; .git copied separately): ruff clean, mypy clean, pytest 212 passed, 2 deselected. Load check: 4 `yes` (PIDs 24162-24165, alive for the whole run, killed by PID, 0 left), 100x the three AFL-028 tests -> 100/100 pass. Orphan check after 6 s: no test process, uuid FIFO, `cat` or `read x` left; two `sleep 10` belong to other agents' long-lived polling shells. AFL-027 hunk `@@ -117,4 +117,20` and executor.py unchanged. Reviewer's pre-exec-window hardening not applied (human decides). See Test (tester, 2026-11-13)
- 2026-11-13 — DoD verified on the reopen, testing -> done (crew-lead)
  - Note: AC boxes are unticked but each AC is evidenced (re-review APPROVE R1-R3 and AC1-AC6; tester PASS on the reopen). Gates re-run by crew-lead at load avg ~3.0: `.venv/bin/ruff check .` "All checks passed!", `.venv/bin/mypy src` "Success: no issues found in 8 source files", `.venv/bin/python -m pytest -p no:cacheprovider` "212 passed, 2 deselected". Stress/load (tester 100/100, earlier 200/200), mutants (M-nodrain, M-unbounded, R2 anchor) and orphan check are recorded above; reproducibility: executor behaviour is code-only (`DRAIN_TIMEOUT_S = 1.0`), no new randomness.
  - Commit-coherence check (crew-lead): a scratch tree of HEAD (`git archive`) plus the working `src/fuzzer/executor.py` and only the AFL-028 hunk of tests/test_executor.py (AFL-027 hunk excluded, so the old parametrised `test_hang_stderr_is_bytes` stays) passes ruff, mypy and pytest (97 passed, 1 deselected; `fuzzer.executor` resolved to the scratch copy in-process). The AFL-028 region uses only HEAD's imports (`os`, `signal`, `subprocess`, `time`) and `run_script`, with `re`/`uuid`/`DRAIN_TIMEOUT_S` imported in-function, so it does not depend on the AFL-027 hunk. Order AFL-028 then AFL-027 is coherent. Scratch deleted.
  - Still open: "verified on a clean checkout" (executor.py and tests/test_executor.py are uncommitted) and "commit references ticket ID" (the commit is the human's). The commit must contain only AFL-028 hunks and lands before AFL-027's.
  - Open, optional follow-up (not a blocker; human decides): the reviewer's pre-exec-window hardening, `subprocess.run(["pkill", "-9", "-f", re.escape(str(tmp_path / "t.sh")) + "$"], check=False)` after `_kill_tree(fifo)` in `test_hang_stderr_written_after_kill_is_drained`. Not applied. It only reduces a possible process leak on the retry path and does not affect test correctness (see Review, 2026-11-13, re-review).

## Test (tester, 2026-11-13)
Verdict: **PASS.** Stays in tickets/testing/, ready for crew-lead DoD. This covers the reopen: a test-only fix in the AFL-028 region of tests/test_executor.py. The executor evidence from 2026-11-12 (200/200 stress, M-nodrain, M-unbounded, boundary check) still applies, because src/ has not changed since.

**Per-AC evidence (re-checked on the current tree):**
- **AC1, unchanged behaviour.** `git diff -U0 tests/test_executor.py` gives two hunks: `@@ -117,4 +117,20` (AFL-027) and `@@ -134,0 +151,81` (AFL-028). The AFL-028 hunk only adds lines, so no AFL-003 test is edited. The executor diff keeps the `ExecResult` field order, `(None, None, True, frozenset(), dt, err or b"")` on timeout, and `stderr=err or b""` on clean and crash. The interface is unchanged. All executor tests pass in the clean copy.
- **AC2, bounded cost.** The only drain `communicate(timeout=DRAIN_TIMEOUT_S)` sits inside `except subprocess.TimeoutExpired`. Clean and crash runs take one `communicate`. `DRAIN_TIMEOUT_S = 1.0` is a module constant.
- **AC3, the fix's test.** The `sh -c 'cat "$1" >/dev/null; echo late >&2' _ <fifo> &` is still forked before `exec 5>"<fifo>"`, so the post-kill causality holds. There is one `f-<uuid4().hex>` FIFO per attempt, and `_kill_tree(fifo)` runs in `finally` for every attempt. The assertions are unchanged (`outcome == "hang"` every attempt; then `mark.exists()`; then `r.stderr == b"late\n"`). Under load: 100/100, see below. I did not repeat the mutants. The reviewer re-ran M-nodrain against this body (10/10 fail), and src/ is unchanged.
- **AC4, a grandchild holds the pipe.** The test is unchanged by the reopen: the `< 0.3 + DRAIN_TIMEOUT_S + 1.0` assertion, the slack comment, and `_kill_pid_file` in `finally`. 100/100 under load, and no `sleep 10` of its own was left behind.
- **AC5, mutants.** Unchanged from the 2026-11-12 record. The reviewer re-ran M-nodrain and the R2 anchor mutant on the reopen.
- **AC6, gates and scope.** `cmp` shows the clean copy's `src/fuzzer/executor.py` and `tests/test_executor.py` are identical to the repo's. The repo's executor.py mtime is Nov 12 20:17, before the reopen. `git diff src/fuzzer/executor.py` is the approved shape: Popen, communicate(timeout), kill, wait, bounded drain, `except BaseException: kill; raise`. Gates are green (below).
- **R1/R2 (reopen).** `_kill_tree` matches `re.escape(str(fifo)) + "( |$)"`. `test_kill_tree_spares_prefixed_neighbour` passes 100/100 under load.

**Clean-copy gates.** Setup: `rsync -a --exclude .venv --exclude results --exclude .git` of the working tree into the job tmp dir, `.git` copied separately, `targets/bin` present through rsync (no rebuild), and `__pycache__` and the tool caches removed. `git status --porcelain` in the copy matches the repo, except for ` D results/.gitkeep` (results/ is excluded). Run with the project venv at load average 1.75:
- `ruff check .` -> All checks passed!
- `mypy src` -> Success: no issues found in 8 source files
- `python -m pytest -p no:cacheprovider` -> 212 passed, 2 deselected in 10.39s (executor.py 95% coverage)

**Load check.**
- Load: 4 `yes >/dev/null &` with PIDs recorded (24162 24163 24164 24165).
- Command, run 100x in the clean copy: `.venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_executor.py -k "written_after_kill or drain_bounded or kill_tree_spares"`. `--collect-only` confirms the selection is 3 tests.
- Result: **100/100 pass, 0 fail**, 226 s. Load average went from 2.29 to 5.73.
- The driver's own "alive" count printed 0/4. That was a zsh artefact: `$PIDS` was not word-split, so the `kill -0` and `kill -9` calls inside the driver failed. `ps` afterwards showed all four `yes` still running with etime 03:51, which covers the whole loop. So the load was in place for the entire run. They were then killed by PID (`kill -9 24162 24163 24164 24165`), and `pgrep -xl yes` returned nothing (rc=1).

**Orphan check.** Run in a separate Bash call after `sleep 6`:
- `pgrep -fl '[p]ytest-of-shinobi07/pytest-[0-9]+/test_(hang_stderr_written_after|hang_drain_bounded_when_d|kill_tree_spares_prefixed_)'` -> none (rc=1)
- `pgrep -fl '[f]-[0-9a-f]{32}( |$)'` -> none (rc=1)
- `pgrep -fl '^[c]at '` -> none (rc=1)
- `pgrep -fl '[r]ead x _ '` -> none (rc=1)
- `pgrep -fl '^[y]es$'` -> none (rc=1)
- `pgrep -fl '^[s]leep (5|10)$'` -> two `sleep 10`, pid 25943 (ppid 52367) and pid 25945 (ppid 50606). Both parents are `/bin/zsh -c source …shell-snapshots…` shells with an etime of about 10 h, the same agents' polling shells the reviewer identified. They are not this test's processes, and I left them alone.

**AFL-027 hunk.** `@@ -117,4 +117,20` is present and unchanged. It still removes the parametrized `test_hang_stderr_is_bytes` and adds `test_hang_stderr_empty_bytes` and `test_hang_stderr_captured_bytes` (marker, 20-attempt retry, `== b"hi\n"`), as described in tickets/done/AFL-027.

**Not done, by instruction.** I did not apply the reviewer's optional `pkill … t.sh$` hardening for the pre-exec fork window; the human decides on it. I did not repeat the 600-run stress.

**Experimental validity.** The reopen changes tests only. Executor behaviour, the replay guarantee, and the metrics are as assessed on 2026-11-12. Scratch copy deleted.

## Review (reviewer, 2026-11-13, re-review)
Verdict: **APPROVE -> testing.** R1, R2 and R3 are met. The AC3 test is not weakened. The residual below is non-blocking: it does not affect any AC, and it does not affect test correctness.

**1. Pattern exactness and the AC3 body.**
- Which processes are matched. `pkill -f` matches against argv joined by spaces:
  - The bg `sh -c 'cat "$1" …' _ <fifo>` and its `cat <fifo>` both have argv ending in the FIFO path, so `re.escape(str(fifo)) + "( |$)"` matches both.
  - A `cat` child of `sh -c` that has forked but not yet exec'd carries the `sh -c` argv, so it is matched too.
  - The uuid makes the token unique per attempt. The anchor stops `x1` from matching `x10`.
- Escaping. `re.escape` emits `\-` and `\.` for the path. macOS ERE accepts them as literals, and R2's positive control proves it on a real `pytest-of-…/pytest-N` path.
- The case the coordinator asked about, `t.sh` killed before it forks the bg `sh`, is fine. Nothing has been spawned yet, and the unused FIFO is harmless.
- **Residual (non-blocking): the pre-exec window.**
  - If `t.sh` is killed after it forks the bg child but before that child execs `sh -c`, the child still carries `t.sh`'s argv (`/bin/sh <tmp>/t.sh`). The FIFO pattern misses it, and it later execs `sh -c` + `cat`, which block forever on that attempt's unique FIFO.
  - I simulated this by widening the window artificially (`( sleep 1.5; exec sh -c … ) &`) in a scratch driver that imports the repo helpers: the current `_kill_tree` leaked 6 processes in 3 attempts.
  - Adding `subprocess.run(["pkill", "-9", "-f", re.escape(str(tmp_path / "t.sh")) + "$"], check=False)` after `_kill_tree(fifo)` leaked 0 in 3 attempts. The pattern is exact: `x1/t.sh$` cannot match `x10/t.sh`.
  - In the real test the window is bash's fork-to-execve (microseconds), and it has to outlast the ~1.3 s before teardown runs (the timeout plus the 1.0 s drain, which the pre-exec child itself triggers by holding stderr).
  - A leak here has no effect on correctness, because the FIFO is unique to the attempt.
  - There is a second race of the same kind that no argv pattern can close: `sh -c` forks `cat` between pkill's process listing and its signal. Closing it needs process groups, which the executor deliberately avoids (Known limitation).
  - So: take the hardening or leave it. It is not a required change.
- **The AC3 scenario is preserved.**
  - The bg `sh -c` is still forked before `exec 5>"$F"`, so it does not hold the write end.
  - `exec 5>` still blocks until `cat` opens the FIFO. SIGKILL to `sleep` closes fd 5. `cat` gets EOF, then `echo late >&2` writes to the inherited stderr pipe strictly after the kill.
  - Evidence: M-nodrain (drain removed, first `TimeoutExpired`'s stderr returned) in a scratch copy, with `-o pythonpath=<copy>/src` and the in-process probe resolving `fuzzer.executor` to the copy. It FAILS `test_hang_stderr_written_after_kill_is_drained` on 10 of 10 runs, each with `assert b'' == b'late\n'` after the marker assert passed. The unmodified code passes 10/10.

**2. R2 test: proves what it claims; cleanup holds on every path.**
- `sh -c 'read x' _ <tmp>/x10/f` is exec'd by the time `Popen` returns, so the argv is already final; the 0.2 s sleep is redundant but harmless.
- `_kill_tree(<tmp>/x1)` must leave it alive. The positive control `_kill_tree(<tmp>/x10/f)` must kill it with SIGKILL. That control is what makes the negative check meaningful: it proves the pattern form matches real argv.
- Mutant re-run by me (anchor `( |$)` removed, in a scratch copy of tests/ + src/ + pyproject): FAILS with "cleanup of x1 killed a process under x10". No `read x` process was left afterwards.
- Cleanup: `finally: p.kill(); p.wait(); stdin.close()` covers an assert failure, a `wait(timeout=5)` timeout, and normal exit. `Popen.kill` on an already-reaped process is a no-op.
- The test checks the anchor, not the uuid. That is the right target, because the anchor is what gives prefix safety.

**3. Scope: PASS.**
- `git diff -U0 tests/test_executor.py` shows `@@ -117,4 +117,20` (AFL-027) and `@@ -134,0 +151,81` (AFL-028, additions only).
- The AFL-027 hunk is textually identical to the one in my first review (split into `test_hang_stderr_empty_bytes` and `test_hang_stderr_captured_bytes`).
- `git diff src/fuzzer/executor.py` is identical to the approved AFL-028 executor diff. The mtime of every `src/` file is Nov 12 or earlier, so nothing in src/ was touched during this reopen.

**4. Orphan check (reviewer, by the protocol):**
- 20 runs of `.venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_executor.py -k "written_after_kill or drain_bounded or kill_tree"`: pass=20, fail=0 (load 2.8).
- Then, in a separate Bash call after a 6 s wait:
  - `pgrep -fl '[p]ytest-of-shinobi07/pytest-[0-9]+/test_(hang_stderr_written_after|hang_drain_bounded_when_d|kill_tree_spares_prefixed_)'`: none;
  - `pgrep -fl '[f]-[0-9a-f]{32}( |$)'`: none;
  - `pgrep -fl '^[c]at '`: none;
  - `pgrep -fl '[r]ead x _ '`: none;
  - `pgrep -fl '^[s]leep (5|10)$'`: two `sleep 10`, ppid 52367 and 50606. These are other agents' `until …; do sleep 10; done` polling shells, the same ones seen in the first review, not this test.

**Gates (load 2.5):** `.venv/bin/ruff check .` -> All checks passed!; `.venv/bin/mypy src` -> Success: no issues found in 8 source files; `.venv/bin/python -m pytest -p no:cacheprovider --no-cov` -> 212 passed, 2 deselected. All scratch copies were deleted.

## Review (reviewer, 2026-11-13)
Verdict: **CHANGES REQUESTED -> in-progress.** The race diagnosis and the per-attempt FIFO fix are sound. The cleanup helper `_kill_tree` has a prefix-collision defect, which the human has made a required fix.

**1. Causal claim: CONFIRMED. The fix addresses the real race; the executor is not implicated.**
- Independent repro (scratch script, repo executor imported read-only; deleted afterwards). It uses the old construction: a shared FIFO `f`, and the pid file kills only the bg subshell. Forced miss = an attempt whose shell forks the bg list and then sleeps without opening the FIFO, killed at 0.3 s. Then one normal attempt. 50 trials per arm, no load:
  - control (no forced miss): marker 50/50, `late` 50/50, 0 `cat` left on the live FIFO;
  - forced miss + shared FIFO: marker 50/50, `late` **31/50**, **19** `cat` left on the live FIFO (exactly one per failure);
  - forced miss + per-attempt FIFO: marker 50/50, `late` 50/50, 0 left.
- So a missed attempt's orphaned `cat` breaks the `exec 5>` rendezvous of the next attempt. The failure signature (marker present, `b''`, one orphan `cat` per failure) matches the field report (4/600, 4 orphan `cat`).
- Correction to the developer's log: in my runs the forced miss reproduces the failure in about 38% of trials, not deterministically. The mechanism holds either way.
- The drain bound is not the cause. In every failure a `cat` stays blocked in `open()` and `late` is never written, so no drain bound could recover it. The stop condition (bound too short) does not apply.
- src/ is untouched by this reopen. `git diff src/fuzzer/executor.py` is the AFL-028 diff the earlier review approved.
- The per-attempt FIFO (`f{i}`) alone removes the race. `_kill_tree` is hygiene on top of it.

**2. `pkill -9 -f <tmp_path>` matching: DEFECT (required fix R1/R2).**
- Prefix collision is real. The pattern is an unanchored ERE matched against the full argv, so `.../test_x1` also matches `.../test_x10/...`. Demonstrated: `_kill_tree(Path(<scratch>/test_x1))` SIGKILLed a `/bin/sh <scratch>/test_x10/u.sh` process (alive before, gone after).
- For this test as written today, tmp_path is `.../pytest-N/test_hang_stderr_written_after0`. The name is truncated to 30 chars, it is the only test with that prefix, and so it is always `...0` within a session. The latent trigger is any repeat or parametrize that numbers it 1..19 (`after1` matches `after10`..`after19`). The human has ruled this a required fix regardless.
- Regex metacharacters: tmp_path is passed to pkill as a raw ERE. A `TMPDIR` containing `+ ( [` etc. would fail to match or match wrongly. Fold this into R1: either match a metachar-free token, or escape the path.
- The pytest process itself is safe: macOS pkill excludes itself and all its ancestors by default (`man pkill`: "-a Include process ancestors… By default… excluded"), and pytest's argv does not contain the per-test tmp_path.
- Concurrent pytest sessions get distinct `pytest-N/` directories, and xdist workers get distinct `popen-gwN/` directories. Both are followed by `/` inside the pattern, so they do not collide across sessions. The collision is only between sibling numbered directories in one basetemp.
- Residual hygiene gap (non-blocking): pkill lists processes and then signals them. A bg subshell that forks `cat` between the two steps leaves that `cat` blocked on its own `f{i}`. With per-attempt FIFOs it cannot affect later attempts. It is only a possible leak, on the rare retry path.

**3. Hunk placement: PASS.** `git diff -U0 tests/test_executor.py` gives `@@ -117,4 +117,20` (AFL-027: `test_hang_stderr_empty_bytes` and `test_hang_stderr_captured_bytes`, as described in AFL-027's done ticket) and `@@ -134,0 +151,60` (AFL-028, additions only, after `test_close_after_run_raised_unlinks`). The AFL-027 hunk is not touched by this reopen.

**4. Known limitation note: PASS.** Technical notes, "Known limitation (human decision, 2026-11-13)": the executor kills only its direct child; this is accepted because the targets never fork; tests must clean up their grandchildren (`_kill_tree`/`_kill_pid_file`); executor.py is deliberately unchanged.

**5. Orphan check, re-run cleanly: PASS on the current code.**
- Run: 50x `.venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_executor.py -k "written_after_kill or drain_bounded"` -> pass=50 fail=0 (load 2.3).
- Check, in a separate Bash invocation after a 6 s wait:
  - `pgrep -fl '[p]ytest-of-shinobi07/pytest-[0-9]+/test_hang_(stderr_written_after|drain_bounded_when_d)'` -> no match (rc=1);
  - `pgrep -xl cat` -> no match (rc=1);
  - `pgrep -fxl 'sleep (5|10)'` -> two `sleep 10`, ppid 52367 and 50606. Those are other agents' `until …; do sleep 10; done` polling shells, not this test.
- My first in-loop snapshot used a loose grep and matched those polling shells and my own waiter. This is likely what made the developer's earlier "4 matches" ambiguous.

**Gates:** `.venv/bin/ruff check .` -> All checks passed!; `.venv/bin/mypy src` -> Success: no issues found in 8 source files; `.venv/bin/python -m pytest -p no:cacheprovider --no-cov` -> 211 passed, 2 deselected (load 1.97).

**Required changes (human decision, 2026-11-13):**
- **R1.** `_kill_tree` must match only this attempt's processes. Two options:
  - preferred: a per-attempt uuid in the grandchild's command line, matched exactly. For example, name the FIFO `f-<uuid4().hex>`, so the blocked `cat` carries it in its argv, and `pkill -9 -f <that token>`. A hex uuid needs no regex escaping;
  - or anchor the tmp_path pattern with a trailing `/` and regex-escape the path.

  Whichever option is used, the AC3 assertions must stay unchanged.
- **R2.** Add a test in the AFL-028 region of tests/test_executor.py. It starts a process under a neighbouring, prefixed directory (for example `<base>/x10/...` when cleaning `<base>/x1`), runs the cleanup, asserts the neighbour is still alive, then kills it by PID in `finally`. Show in the Log that this test FAILS against the current unanchored `_kill_tree` (mutant in a scratch copy, deleted afterwards) and passes on the fix.
- **R3.** On the fixed code, record an orphan check in the Log using the protocol in point 5: run pgrep with an exact pattern, in a separate shell invocation, about 5 s after the run, and write down the pattern and the result.

The human judges the stress and mutant evidence for the race fix sufficient. Do not repeat the 600-run stress.

## Review
Verdict: **APPROVE -> testing** (reviewer, 2026-11-12). Gates: `.venv/bin/ruff check .` clean, `.venv/bin/mypy src` clean, `.venv/bin/python -m pytest tests/test_executor.py` 16 passed. Full `pytest` was not run by the reviewer because AFL-007 is running concurrently; the tester runs it.

CPython semantics, checked in the installed 3.12.9 `subprocess.py`:
- `communicate` sets `_communication_started = True` in a `finally` (l.1227-1228), so it is set even when `TimeoutExpired` is raised. `_communicate` builds `_fileobj2output` only when `not _communication_started` (l.2088-2093), so the second call appends to the same per-`Popen` list. `_check_timeout` joins that whole list (l.1257-1258), which makes `e2.stderr` cumulative (Q2 holds).
- The drain's trailing `self.wait(timeout=remaining)` (l.2149) returns at once because the child was already reaped by `p.wait()`. The drain's `TimeoutExpired` can therefore only come from the read loop, as the notes claim.
- Second call with `input=None`: the l.1185 guard does not fire, the stdin flush/close is skipped (l.2071), and stdin is not registered (l.2106). No input is re-sent.
- `run()` (l.550-575) is the template: kill, wait, and a bare `except: kill; raise`. The new body matches it.

AC1, unchanged behaviour: PASS.
- `ExecResult` and `outcome` are untouched.
- The timeout branch returns `(None, None, True, frozenset(), dt, bytes)` as before.
- The clean/crash path reads `p.returncode` after `communicate`, which waits, as `run()` did through `poll()`. `stderr=err or b""` is the same value `CompletedProcess.stderr` carried.
- `stdin=PIPE` is set always, as `run(input=b"")` did, and `stdout=DEVNULL` is unchanged.
- `exec_time` now stops after the drain (Q3). No consumer reads hang `exec_time`.
- The `git diff` of tests/test_executor.py has two hunks. The first (l.117) is AFL-027's. The second, appended after `test_close_after_run_raised_unlinks`, is AFL-028's and only adds lines. No AFL-003 test is edited by AFL-028.

AC2, bounded cost: PASS.
- The drain is reachable only from `except subprocess.TimeoutExpired`, so clean and crash runs take a single `communicate`.
- The added cost is at most `DRAIN_TIMEOUT_S = 1.0` (a module constant) plus one select iteration. The kill+wait already existed.

AC3, test of the fix: PASS on construction.
- The FIFO chain makes `late\n` causally after the kill, so M-nodrain fails by causality.
- The bg list is forked before `exec 5>`. The marker and retry follow the AFL-027 pattern, and the exact `== b"late\n"` assertion runs after the loop.
- The developer's 200/200 under 10-core load predates the mypy edit. The edit is behaviour-neutral: `e.stderr or b""` is then passed through `err or b""` again in the return, so the result is identical for `None`, `b""` and non-empty bytes. The tester re-runs it on the final code.

AC4, grandchild holds the pipe: PASS.
- Wall-clock is asserted `< 0.3 + DRAIN_TIMEOUT_S + 1.0`, with the slack comment present.
- `stderr == b"pre\n"` pins the cumulative-stderr path.
- `DRAIN_TIMEOUT_S` is imported inside the function, and the pid is SIGKILLed in `finally` for every attempt.

AC5, mutants: PASS (re-run by the reviewer).
- M-nodrain (kill+wait, return the first `TimeoutExpired`'s stderr) fails `test_hang_stderr_written_after_kill_is_drained`.
- M-unbounded (`communicate()` without timeout) fails `test_hang_drain_bounded_when_descendant_holds_stderr`.
- `sys.modules["fuzzer.executor"].__file__` resolved to the copy each time, and the copy was deleted.
- `pgrep -x cat` and `pgrep -fx "sleep 10"` were empty afterwards.

AC6, scope: PASS. The AFL-028 changes are limited to src/fuzzer/executor.py and the appended hunk of tests/test_executor.py. The other working-tree diffs belong to other tickets (AFL-007, AFL-009, AFL-027).

BaseException parity: holds. The new body keeps `run()`'s structure, including where a handler-raised exception escapes.
- A KeyboardInterrupt during the first `communicate` is handled by communicate's own 0.25 s sigint wait, then `except BaseException: kill; raise`. `__exit__` sees KI and returns without `wait()`. This is the same as `run()`.
- A KeyboardInterrupt during `p.wait()` or the drain escapes the sibling `except BaseException`, as in `run()`, but the child is already SIGKILLed (or reaped). `__exit__` on KI does not wait, and on any other exception its `wait()` returns at once.
- `__exit__` cannot block on a live child on any path.

Non-blocking notes:
1. tests/test_executor.py `test_hang_stderr_written_after_kill_is_drained`: `_kill_pid_file` kills the `{ ... }` subshell, not its child `cat`. If an attempt's `sh` is killed after forking the bg list but before `exec 5>"$F"`, that `cat` stays blocked in `open()` on the FIFO. A later successful attempt unblocks it, so it leaks only when all 20 attempts fail, which is a path where the test already fails. Possible hardening: run `exec cat` in the background, or open the FIFO non-blocking in cleanup.
2. In both tests, `P` keeps the previous attempt's pid if an attempt is killed before `echo $! > "$P"`. Cleanup would then SIGKILL an already-dead pid, which could in theory be a recycled one. Only the retry path is affected. Truncating `P` at the start of each attempt would close this.
3. The AC4 bg `sleep 10` can outlive its attempt by up to 10 s if the kill lands before `echo $!`. This is bounded and self-terminating. The tester's `pgrep sleep` check should allow for it.
4. No test exercises non-empty input on the timeout path, so a regression that passes `data` to the drain `communicate` would go uncaught. The code is correct by inspection, and the notes already flag this.
