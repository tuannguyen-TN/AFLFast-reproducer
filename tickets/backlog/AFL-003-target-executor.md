---
id: AFL-003
title: Target executor (timeout + signal capture)
requirement: FR-2
paper_ref: AFL whitepaper (target execution, crash/hang detection)
module: src/fuzzer/executor.py
depends_on: []
status: backlog
owner: developer
---

## Goal
Run the target on one input safely and report what happened (FR-2): exit status,
terminating signal, and coverage, with a timeout so a hanging input cannot stall
the campaign. Crash classification here is the input to crash saving and dedup
(FR-6, AFL-013).

Open questions (PRD silent or ambiguous; resolve before leaving backlog):
- **ASan exit behaviour.** By default AddressSanitizer reports an error and exits
  with a non-zero code, not SIGABRT. tlv_parser's planted bug is caught by ASan.
  If only SIGSEGV/SIGABRT count as crashes, that bug may not be detected unless
  ASan is configured to abort (e.g. `ASAN_OPTIONS=abort_on_error=1`) or the crash
  rule is widened. This affects SC1.
- The PRD does not give a timeout value, and does not say whether a timeout is
  reported as a hang, counted as a crash, or ignored.
- FR-2 returns coverage, but INDEX lists no dependency on AFL-002. Should the
  executor call coverage.py, or return raw data for the caller to interpret?
- FR-6 lists `executor.py` as a module for "crashing inputs saved with signal +
  faulting context". This ticket covers classification only. Saving is in
  AFL-013. Confirm that split.
- FR-2 says "stdin/file input". Must both modes be supported, or is either one
  enough? Both current targets read stdin.

## Acceptance criteria
- [ ] Executes the target binary on one given input, delivered via stdin and/or a
      file (see open question).
- [ ] Enforces a timeout: a target that runs past the limit is killed, and the
      result says that the timeout fired.
- [ ] Returns (exit status, terminating signal, coverage) for every run.
- [ ] A run terminated by SIGSEGV or SIGABRT is classified as a crash.
- [ ] A run that exits normally with no signal is not classified as a crash.
- [ ] Runs only local binaries passed in by the caller. It makes no network calls
      (NFR-6).
- [ ] Throughput is measured on a toy target and reported against the AFL-001
      baseline of ~24 execs/sec (naive: fresh ASan process + fresh shm per exec).
      Either outcome passes: (a) measured throughput meets NFR-3 (≥500 execs/sec on
      a laptop), via a fork server and/or reused bitmap if needed; or (b) it falls
      short, and the shortfall, the executor bottleneck, and its campaign-budget
      impact (AFL-011 trial counts/durations) are documented as a threat to validity
      per NFR-3. The chosen outcome is recorded in this ticket's log.

## Technical notes (architect)
- **Interfaces (`executor.py`).** This is the FR-2 contract. Corpus, fuzzer and dedup
  all consume `ExecResult` and nothing else:
  ```python
  @dataclass(frozen=True)
  class ExecResult:
      exit_status: int | None   # None if killed by a signal
      signal: int | None        # terminating signal number
      timed_out: bool
      edges: frozenset[int]     # empty if timed_out
      exec_time: float          # wall-clock seconds for this run
      stderr: bytes             # ASan report; consumed by dedup (AFL-013)
      @property
      def crashed(self) -> bool: ...  # signal in {SIGSEGV, SIGABRT} and not timed_out

  class Executor:
      def __init__(self, target: Path, timeout_s: float = 1.0) -> None: ...
      def run(self, data: bytes) -> ExecResult: ...
      def close(self) -> None: ...
  ```
- Executor owns a `coverage.ShmBitmap` (AFL-002). It resets the bitmap before each run
  and returns interpreted edges, which answers open question 3. So this ticket
  depends on AFL-002.
- Implementation: `subprocess.run([target], input=data, stdout=DEVNULL, stderr=PIPE,
  timeout=timeout_s, env=...)` with `shell=False`. A negative returncode gives the
  signal.
- **Throughput decision rule.** Baseline ~24 execs/sec (one ASan process + fresh shm
  per exec, AFL-001/ADR-0001). Start with one process per run. If measured throughput
  meets NFR-3 (≥500 execs/sec), keep it simple. If not, either add a fork server /
  reused bitmap to reach it, or — per NFR-3's escape clause — document the shortfall
  and its campaign-budget impact (AFL-011 trial counts/durations) as a threat to
  validity. Decide and record which in this ticket's log.
- **ASan config** (proposed default — confirm, → ADR-0002 (to write)): the executor
  sets `ASAN_OPTIONS=abort_on_error=1:detect_leaks=0:symbolize=1` over the inherited
  env. Every ASan finding, including an ASan-intercepted SEGV, then ends in SIGABRT
  and counts as a crash under FR-2 as written. No PRD change needed. `detect_leaks=0`
  because LeakSanitizer exits non-zero on leaks and is unsupported on macOS.
- **Timeout** (proposed default — confirm): fixed at 1.0 s, a constructor parameter
  recorded in `run.json`. On timeout the child is killed, `timed_out=True`, coverage
  is discarded, and it is **not** a crash. It is counted as a "hang" in metrics only
  and not analysed.
- **Input delivery** (proposed default — confirm): stdin only, since both targets
  read stdin. Add file mode when a target needs it.
- **Split with AFL-013** (proposed default — confirm): the executor only classifies
  and captures stderr. fuzzer.py writes the crash files (AFL-007), and dedup.py
  buckets them offline (AFL-013).
- No RNG and no knowledge of the schedule. Runs only the `target` path it is given,
  makes no network calls (NFR-6).

## Test approach (tester)
Unit/integration tests with small helper targets that exit cleanly, segfault,
abort and hang. Assert classification and that the timeout fires within a bound.

## Log
- 2026-11-07 — created (req-engineer)
- 2026-11-07 — AC added from AFL-001 spike (ADR-0001)
- 2026-11-07 — technical note reconciled with throughput AC (decision rule)

## Notes from AFL-002 review/test
Follow-ups (not ACs; address while implementing):
- `ShmBitmap.close()` is not idempotent, and unlink is skipped if `shm.close()` raises. The executor owns the bitmap: wrap its lifetime in `try/finally`.
- Fail fast if the first seed yields an empty edge set (AFL's "no instrumentation detected"), e.g. a target built without trace-pc-guard.
- Measure NFR-3 throughput on the actual `-O0` ASan build (ADR-0001), not an optimised one.
- Test `ShmBitmap.reset()` and bitmap reuse across consecutive runs (no stale edges).
- `needs_clang` skipif in tests checks `clang` on PATH, not the Homebrew clang the Makefile prefers; align it.
- Pass `ASAN_OPTIONS` over the inherited env (as in the ASan note above) rather than stripping the env.
- Resolve the target binary to an absolute path before exec.
- `cov_rt.c` should fail loudly (non-zero exit / stderr) if `shm_open` fails while `FUZZ_SHM_NAME` is set, instead of silently running uninstrumented.
