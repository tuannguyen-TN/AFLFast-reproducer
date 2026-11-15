---
id: AFL-027
title: De-flake test_hang_stderr_is_bytes (no timing dependence, no quarantine)
requirement: NFR-1 (reproducibility), NFR-5 (code quality); deterministic DoD gate (CLAUDE.md §7, gate_ticket_done.py)
paper_ref: n/a (test reliability)
module: tests/test_executor.py (only; src/fuzzer/executor.py unchanged unless a real executor bug is found, then stop and report)
depends_on: [AFL-003, AFL-028]
status: done
owner: developer
---

## Goal
Make `tests/test_executor.py::test_hang_stderr_is_bytes` deterministic. On one
cold run, its `echo hi >&2; exec sleep 5` case got `r.stderr == b''` instead of
`b'hi\n'` with `timeout_s=0.3`. It then passed 8 times out of 8. The done gate
(`.claude/hooks/gate_ticket_done.py`) runs the full pytest suite on every ticket
close. A flaky test either blocks closes at random or teaches the crew to re-run
until green, and then the gate stops being taken seriously. The test is
timing-sensitive under load, and the campaign may run trials in parallel.

**Priority:** the next pull after AFL-009.

## Acceptance criteria
- [x] **AC1, no timing dependence.** The `b"hi\n"` case no longer depends on
      scheduling timing. Use one of the two approaches below and record which one
      in the Log:
      - **(a) preferred, handshake.** `isinstance(r.stderr, bytes)` is asserted
        unconditionally. The content assertion `r.stderr == b"hi\n"` is made only
        after the child has proved it wrote. For example, the child writes to
        stderr and then signals through a marker file or pipe the test controls, or
        blocks on something the test controls. If the content assertion is
        conditional on that proof, the test must also assert that the proof was
        observed. A content check that silently never runs fails this AC.
      - **(b) margin.** A timeout margin large enough that a cold start cannot race
        the write. The chosen value and the reason for it are written in a comment
        next to it.
- [x] **AC2, no quarantine.** The test file contains no `xfail`, `skip`, `flaky`
      or rerun-plugin marker or decorator for this test, and no rerun plugin is
      added to `requirements.txt` or `pyproject.toml`.
- [x] **AC3, the test still bites.** Each of these mutants, applied to a throwaway
      copy of `src/fuzzer/executor.py` outside the repo (module path verified,
      copy deleted afterwards, as in AFL-023 AC4), makes the reworked test fail:
      - **M-drop:** on the `TimeoutExpired` path, return `b""` instead of
        `e.stderr or b""`.
      - **M-decode:** on the `TimeoutExpired` path, return stderr that is
        mis-decoded or not `bytes` (e.g. `(e.stderr or b"").decode()`, or `None`).
      The developer records each mutant and the failing test id in the Log, and the
      reviewer re-runs them. The unmodified executor passes.
- [x] **AC4, stress check.** The reworked test passes **200 out of 200** in a loop
      while the machine is under CPU load: N busy loops running alongside, where N
      = physical core count (`sysctl -n hw.physicalcpu` on macOS). The exact
      command (load generator, loop and pytest invocation) and the result are
      recorded in the Log.
- [x] **AC5, scope.** The diff under `src/`, `tests/`, `harness/`, `targets/` and
      `docs/` changes only `tests/test_executor.py` (ticket and board files
      excepted). `src/fuzzer/executor.py` is unchanged. If the investigation shows
      a real executor bug (see Technical notes, cause 2), the developer stops and
      reports to the orchestrator; that fix gets its own ticket. The `exec sleep 5`
      → `b""` case keeps its intent. `ruff check . && mypy src && pytest` pass.

## Technical notes (architect)
- **Hang path today.** `Executor.run` calls `subprocess.run(..., stderr=PIPE,
  timeout=...)` and on `TimeoutExpired` returns `e.stderr or b""`. On POSIX,
  CPython's `run()` kills the child and calls `wait()`. It does **not** read the
  pipe again, so `e.stderr` holds only what `_communicate` had read before the
  deadline.
- **Root cause, to be confirmed by the developer before changing the test.**
  There are two candidates:
  1. **Test race (likely).** Under cold-start load, `/bin/sh` startup and the
     `echo` do not finish inside 0.3 s, so nothing was written before the kill. This
     is a test bug, and this ticket fixes it.
  2. **Undrained pipe (would be an executor bug).** The child wrote `hi\n` before
     the deadline, but `_communicate` had not read it when `TimeoutExpired` was
     raised, and `run()` does not drain the pipe after the kill. If this is
     reproducible (for example, the handshake proves the write happened and
     stderr is still `b''`), it is an executor data-loss bug. **Stop and report.**
     Do not patch `executor.py` under this ticket.
  The handshake in AC1(a) separates the two causes: proof of the write plus an
  empty stderr points to cause 2.
- **Handshake options for AC1(a); the architect may choose.** (i) The child runs
  `echo hi >&2; : > "$MARK"; exec sleep 5`, and the test asserts the content only
  when `MARK` exists. The test also requires that `MARK` exists in this run, or
  loops `run()` until it does with a bounded attempt count that is asserted. (ii)
  The child writes and then blocks reading a FIFO the test controls. The test
  drives the executor from a thread and releases the FIFO only after the timeout
  path. Prefer whichever is simpler and still proves the write happened.
- **If AC1(b) is used,** state why the margin is enough: cold `/bin/sh` startup
  under N-core load, against the observed failure at 0.3 s. Keep the hang test's
  wall-clock bound of `timeout + 1` s (as in `test_hang`) so the suite stays fast.
- **Stress load example (macOS):**
  `N=$(sysctl -n hw.physicalcpu); for i in $(seq $N); do (yes > /dev/null &); done;`
  then `for i in $(seq 200); do pytest -q "tests/test_executor.py::test_hang_stderr_is_bytes" || break; done`,
  then `pkill yes`. Record the actual command used.

- **Until AFL-028 lands** (human decision, 2026-11-12): the new
  `test_hang_stderr_captured_bytes` can fail about 1 in 400 runs in the done gate
  (the undrained-pipe race, cause 2). If it does, the failure is attributed to
  AFL-028, not re-run until green.

## Test approach (tester)
Run the gates in a clean clone. Re-run the AC4 stress loop (200/200 under
N-physical-core load) and confirm the Log command reproduces it. Re-apply M-drop
and M-decode to a throwaway copy outside the repo and confirm the reworked test
fails on each. Confirm there are no quarantine markers or rerun plugins. Confirm
that only `tests/test_executor.py` changed and `src/fuzzer/executor.py` is
byte-identical.

## Log
- 2026-11-12 — created (req-engineer) after one cold-run failure of
  `test_hang_stderr_is_bytes[echo hi >&2; exec sleep 5-hi\n]` (stderr `b''`,
  `timeout_s=0.3`; then 8/8 passes). Priority: next pull after AFL-009.
  Option (a) preferred, no quarantine, 200/200 stress under load (human decision)
- 2026-11-12 (developer) — root cause: cause 1 (test race). With the marker handshake, every run where the marker existed had stderr == b"hi\n" (200/200 stress, no marker-present/empty-stderr case), so no executor data-loss bug; executor.py untouched.
- AC1: option (a)(i). `test_hang_stderr_is_bytes` split into `test_hang_stderr_empty_bytes` (`exec sleep 5` -> b"") and `test_hang_stderr_captured_bytes` (`echo hi >&2; : > MARK; exec sleep 5`). bytes+hang asserted every attempt; run retried up to 20x until MARK exists; `assert mark.exists()` then `stderr == b"hi\n"`.
- AC2: no xfail/skip/flaky/rerun markers; no deps added.
- AC3 (throwaway copy of src/, `pytest -o pythonpath=<copy>/src`, `fuzzer.executor.__file__` verified to resolve to copy, copy deleted): unmodified 14 passed; M-drop (`b""`) fails test_hang_stderr_captured_bytes; M-decode (`(e.stderr or b"").decode()`) fails test_hang_stderr_empty_bytes and test_hang_stderr_captured_bytes; M-None fails both likewise. Note: repo pyproject `pythonpath=["src"]` shadows PYTHONPATH, hence `-o pythonpath`.
- AC4: N=10 (hw.physicalcpu); 10x `yes >/dev/null &`; `for i in 1..200: .venv/bin/python -m pytest --no-cov -p no:cacheprovider tests/test_executor.py::test_hang_stderr_empty_bytes tests/test_executor.py::test_hang_stderr_captured_bytes` -> 200/200 pass. Load killed with `pkill -x yes`; `pgrep -x yes` = 0.
- AC5: only tests/test_executor.py changed; src/ diff empty.
- moved in-progress -> review (developer)
- 2026-11-12 (reviewer) — CHANGES REQUESTED, review -> in-progress (bounce 1). AC2 met (no quarantine markers, no deps). AC3 met: reviewer re-ran on a throwaway copy via `pytest -o pythonpath=<copy>/src`, `sys.modules["fuzzer.executor"].__file__` printed in-process = the copy; unmodified 14 passed; M-drop fails test_hang_stderr_captured_bytes; M-decode and M-None fail both hang tests; copy deleted. Gates green (ruff, mypy, `94 passed, 1 deselected`). src/ diff empty. Reasons:
  1. **Cause 2 reproduced (AC5 stop-and-report trigger).** With the unmodified executor, the exact test body (`echo hi >&2; : > MARK; exec sleep 5`, timeout 0.3) under 10x `yes` load gave marker present + stderr `b''` in 1/400 runs (398 `(True, b'hi\n')`, 1 `(False, b'')`). Without load, a write placed near the deadline (`sleep 0.08`/`0.10` before the echo) gave marker + `b''` in 2/100 and 3/100. Mechanism (CPython 3.12.9 source): POSIX `Popen._communicate` calls `_check_timeout` right after `select()` returns and *before* reading the ready fds, and `run()` on `TimeoutExpired` only does `kill()` + `wait()`, no drain. Bytes the child wrote before the kill, even before the deadline if the parent wakes late, are dropped. The developer Log line "no executor data-loss bug" is falsified. It is an executor property and needs its own ticket (drain stderr after kill, bounded); not fixable under this ticket per AC5.
  2. **AC1 not met.** The content assertion still depends on scheduling timing: when the write lands in the window above, the test breaks on the marker and fails `stderr == b'hi\n'`. Measured residual about 1/400 per test run under load. The 200/200 in AC4 does not exclude it (expected 0.5 failures at that rate).
  3. **The test diff is otherwise sound; do not rework it.** Marker logic is correct (separate file from the rewritten t.sh, fresh tmp_path, break on first appearance, bounded 20 with asserted proof). The retry discards only no-marker runs, which carry no information. The empty case keeps its intent and catches M-decode/M-None. Recommended path, for the orchestrator/human: open an executor ticket (drain-after-kill), make AFL-027 `depends_on` it, then re-run AC3/AC4 unchanged. Alternative: re-scope AC1 by human decision.
- 2026-11-12 — human decision: option 1 with changes. Executor fix filed as AFL-028
  (drain stderr after the timeout kill, bounded); depends_on += AFL-028. Rejected:
  re-scoping AFL-027, and folding the fix into AFL-027 (executor changes before the
  freeze must be separately findable and reviewable). The test diff is kept
  unchanged; after AFL-028 lands, AC3 (mutants) and AC4 (stress) are re-run against
  the fixed executor. This ticket's diff stays uncommitted until AFL-028 lands.
  ACs otherwise unchanged (req-engineer)
- 2026-11-12 (developer) — re-run after AFL-028 landed; test diff unchanged (hunk `@@ -114` only; AFL-028 hunk `@@ -132,3 +148,54` untouched). AC1 approach stays (a)(i) marker handshake. executor.py not modified by this ticket (its diff is AFL-028's).
- AC3 re-run vs the fixed executor (throwaway copies of src/ under the job tmp dir, `-o pythonpath=<copy>/src --no-cov -p <plug>`; plugin printed `sys.modules["fuzzer.executor"].__file__` = `<copy>/src/fuzzer/executor.py` for each run; copies deleted). Mutants applied on the final `ExecResult(... time.monotonic() - start, err or b"")` of the TimeoutExpired path (line 72); no adaptation needed. Unmodified: 3 hang_stderr tests pass. M-drop (`err or b""` -> `b""`): FAILS test_hang_stderr_captured_bytes and AFL-028's test_hang_stderr_written_after_kill_is_drained. M-decode (`(err or b"").decode()`): FAILS test_hang_stderr_empty_bytes, test_hang_stderr_captured_bytes, test_hang_stderr_written_after_kill_is_drained.
- AC4 re-run: N=10 (`sysctl -n hw.physicalcpu`); `for i in $(seq 10); do (yes > /dev/null &); done`; `for i in $(seq 200); do .venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_executor.py::test_hang_stderr_empty_bytes tests/test_executor.py::test_hang_stderr_captured_bytes; done` -> 200/200 pass. `pkill -x yes`; `pgrep -x yes` empty; no `cat` left; one stray `sleep 60` belongs to another parent process (not this test's sleep 5/10), left alone.
- Gates: ruff clean, mypy clean, full pytest green.
- moved in-progress -> review (developer)
- 2026-11-12 (reviewer) — APPROVED, review -> testing. Scope: hunk `@@ -114` of tests/test_executor.py only (AFL-028 hunk and executor.py are context). AC1 met, (a)(i): `isinstance(r.stderr, bytes)` + hang asserted on every attempt (tests/test_executor.py:119, :132); proof asserted before content (:135, :136). The marker proves the write reached the pipe before the kill: `echo` and `:` are sh builtins and run in order, so write(2) of 3 bytes (< PIPE_BUF) completes before the open(O_CREAT). A killed child makes no later syscalls, and there is no descendant, so no stale marker is possible. With the AFL-028 drain (executor.py:64-72; CPython keeps `_fileobj2output` across `communicate` calls), the drain path runs on every hang attempt. This test does not force the late-read case; AFL-028's FIFO test covers that. Retry cannot mask a regression: the retry condition (marker) does not depend on executor stderr handling. Bound: about 0.3 s per miss; measured 20 forced misses = 6.1 s (single-process slow shell); hard ceiling about 20 x (0.3 + DRAIN_TIMEOUT_S) only if a descendant held stderr, which this body cannot create. AC2 met (grep: no xfail/skip/flaky/rerun; the pyproject diff is AFL-015's ruff exclude). AC3 re-run (throwaway copies, `-o pythonpath=<copy>/src --no-cov`, in-process `sys.modules["fuzzer.executor"].__file__` = the copy each run, copies deleted): base 16 passed; M-drop (line 72 `b""`) FAILS captured_bytes (b'' == b'hi\n'); M-decode (line 72 `.decode()`) FAILS empty_bytes + captured_bytes. Extra: M-nocap (stderr=DEVNULL) FAILS captured_bytes; M-early (timeout x0.001) FAILS captured_bytes on "never reached the marker" in <1 s, so the loop terminates and fails. AC4 re-run: N=10, `for i in $(seq 10); do (yes > /dev/null &); done`; 200x `.venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_executor.py::test_hang_stderr_empty_bytes tests/test_executor.py::test_hang_stderr_captured_bytes` -> pass=200 fail=0 (170 s, 10 yes alive at end); `pkill -x yes`, 0 left. AC5 met: AFL-027 diff is tests only; ruff clean, mypy clean, full pytest 174 passed, 2 deselected. Non-blocking: the 20-attempt bound has no rationale comment (AC1(a) does not require one).
- 2026-11-12 (tester) — PASS; stays in testing/ for crew-lead close. Heavier stress (20 `yes` = 2x physicalcpu, plus 2 concurrent full-file pytest runs x 300 iterations): test_hang_stderr_empty_bytes 600/600, test_hang_stderr_captured_bytes 600/600. Cold start (60x fresh interpreter, `-p no:cacheprovider`, under load): 60/60 for both. Gates: ruff clean, mypy clean, pytest 186 passed / 2 deselected, `-m slow` 2 passed. Findings outside AFL-027 (AFL-028 drain test 4/600 + orphan cats; AFL-003 asan test 129/600 under a load spike) are listed in the Tester section.
- 2026-11-12 — DoD verified, testing -> done (crew-lead)
  - Note: AC boxes are unticked but each AC is evidenced (reviewer APPROVED AC1-AC5 met;
    tester PASS). Gates re-run by crew-lead at load avg ~2.5: ruff "All checks passed!",
    mypy "Success: no issues found in 8 source files", pytest "186 passed, 2 deselected".
    Still open: "verified on a clean checkout" (tests/test_executor.py is uncommitted) and
    "commit references ticket ID" (the commit is the user's). This ticket's commit must land
    after AFL-028's, since both edit tests/test_executor.py (AFL-027 = hunk `@@ -114` only).
    Tester findings F1 (AFL-028 drain test 4/600 under load, stale FIFO reader) and F2
    (AFL-003 ASan test times out under heavy load) are outside this ticket and still need
    routing.
- 2026-11-13 — AC boxes ticked from recorded review/test evidence before commit (developer)

## Tester (2026-11-12)
Verdict: **PASS** (AFL-027 scope: hunk `@@ -114` of tests/test_executor.py; AFL-028 hunk and executor.py treated as baseline).

1. **Heavier stress (different shape from reviewer's).** `N=$((2*$(sysctl -n hw.physicalcpu)))` = 20; `yes > /dev/null &` x20 (PIDs recorded); per iteration, 2 concurrent `.venv/bin/python -m pytest -q --no-cov -p no:cacheprovider --junitxml=... tests/test_executor.py`, 300 iterations = 600 full-file runs; tallied from the junit XML. Results: test_hang_stderr_empty_bytes 600/600, test_hang_stderr_captured_bytes 600/600. 20/20 `yes` alive at the end of the stress phase and at the end of the cold phase. Load average peaked around 74 (other agents' work added to it).
2. **Cold start.** 60x `.venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_executor.py::test_hang_stderr_empty_bytes tests/test_executor.py::test_hang_stderr_captured_bytes`, with the 20 `yes` still running: 60/60 rc=0 (both tests passed in every junit file).
3. **Independent probe of the handshake premise** (out-of-repo script, exact test body, real executor, timeout 0.3, 1000 runs under the same load): marker present 510, all with stderr `b'hi\n'`; marker absent 490, all with `b''`; **marker present but wrong stderr: 0**. Under this load, about 49% of attempts miss the marker. P(20 consecutive misses) is about 0.49^20, roughly 6e-7, so the 20-attempt bound holds. At a miss rate of about 0.8 it would be about 1%, which is the ceiling to watch if the gate ever runs under heavier parallel load (non-blocking, as the reviewer noted: no rationale comment for 20).
4. **Gates (unloaded).** `ruff check .` all passed; `mypy src` no issues (8 files); `.venv/bin/python -m pytest` 186 passed, 2 deselected; `.venv/bin/python -m pytest --no-cov -m slow` 2 passed.
5. **Coverage-loss check.** The original parametrised test asserted `outcome == "hang" and isinstance(stderr, bytes) and stderr == want` for both cases. Now: the empty case asserts all three in one line (tests/test_executor.py:119). In the captured case, hang + bytes are asserted on every attempt (:132), then proof (:135), then exact `b"hi\n"` (:136). `== b"..."` on bytes rejects a decoded str and `None` in both tests, so "bytes, never None, never decoded" is still asserted in both cases. AC2: grep finds no xfail/skip/flaky/rerun; the requirements.txt diff is empty, and the pyproject diff is only AFL-015's ruff exclude.
6. **AFL-028 regression (alongside).** Unloaded: pass. Under the step-1 load: test_hang_drain_bounded_when_descendant_holds_stderr 600/600; **test_hang_stderr_written_after_kill_is_drained 596/600** (`assert b'' == b'late\n'`, runs 26a/43b/243b/258a, ~2.6 s each). See finding F1.

Findings (not AFL-027 defects; for the orchestrator to route):
- **F1 (AFL-028 test, tests/test_executor.py:162-179).** There were 4/600 failures and exactly 4 orphaned `cat <tmp>/test_hang_stderr_written_after0/f` processes (PPID 1). They map 1:1 to the failing runs: pytest-1829/1863/2280/2311 appear in the logs of the 4 failing runs. The likely mechanism is a stale FIFO reader. On a miss attempt, `_kill_pid_file` kills the `{ ... } &` subshell but not its `cat`, which stays blocked in open(O_RDONLY) on the same FIFO (same tmp_path across attempts). On the next attempt, `exec 5>` can pair with that stale reader before the new `cat` has opened the FIFO. After the kill, the stale cat gets EOF and exits without echoing. The new cat then blocks forever with no writer, so `late` is never written, the 1.0 s drain expires on `b''`, and the new cat is orphaned. This points to a test bug (the descendant never wrote), not an executor data-loss bug, but it is a hypothesis from the 1:1 correlation and the ~2.6 s durations. It was not separately reproduced. All 4 orphans were killed with `pkill -f "test_hang_stderr_written_after0/f"`; 0 remain.
- **F2 (AFL-003 test, tests/test_executor.py:77-81, `ex` fixture default timeout 1.0 s at :71).** test_asan_crash_despite_parent_env failed 129/600 with `('hang', None) != ('crash', SIGABRT)`, all inside iterations 236-300 (from 21:14, during a load spike to ~74), and passed 5/5 unloaded afterwards. Under extreme contention, the ASan report and abort exceed the 1.0 s timeout. This is pre-existing and load-sensitive: it would bite the done gate if the gate runs during a heavy campaign.

Cleanup: own `yes` PIDs killed by PID, `kill -0` on all 20 = 0 alive, `pgrep -x yes` empty; orphan cats 4 -> 0; two `sleep 10` processes belong to another agent's polling loops and were left alone. Scratch dir deleted. No git writes by tester.
