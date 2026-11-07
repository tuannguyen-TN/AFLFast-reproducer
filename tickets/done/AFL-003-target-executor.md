---
id: AFL-003
title: Target executor (timeout + signal capture)
requirement: FR-2
paper_ref: AFL whitepaper (target execution, crash/hang detection); ASan config per ADR-0002
module: src/fuzzer/executor.py (+ targets/cov_rt.c fail-loud, tests/ needs_clang alignment)
depends_on: [AFL-002]
status: done
owner: tester
---

## Goal
Run the target on one input safely and report what happened (FR-2): exit status,
terminating signal, and coverage, with a timeout so a hanging input cannot stall
the campaign. Every run ends in exactly one of three outcomes: clean, crash or
hang. Crash classification here is the input to crash saving (AFL-007) and dedup
(FR-6, AFL-013).

Open questions (all resolved 2026-11-07):
- ~~**ASan exit behaviour.** By default AddressSanitizer reports an error and exits
  with a non-zero code, not SIGABRT. tlv_parser's planted bug is caught by ASan.
  If only SIGSEGV/SIGABRT count as crashes, that bug may not be detected unless
  ASan is configured to abort (e.g. `ASAN_OPTIONS=abort_on_error=1`) or the crash
  rule is widened. This affects SC1.~~
  **Resolved (human, 2026-11-07): adopt ADR-0002.** The executor replaces any
  inherited `ASAN_OPTIONS` with `abort_on_error=1:detect_leaks=0:symbolize=1`.
  An inherited value cannot override it (same failure class as the AFL-002
  `CFLAGS` bug). tlv_parser's overflow is value-triggered, and coverage will not
  guide the fuzzer to it, so the ASan abort is the only thing that makes it a
  countable crash. FR-2's crash rule is unchanged.
- ~~The PRD does not give a timeout value, and does not say whether a timeout is
  reported as a hang, counted as a crash, or ignored.~~
  **Resolved (human, 2026-11-07):** the timeout is 1.0 s, set in the constructor.
  A timeout is outcome `hang`. A hang is never a crash and never clean, and it
  does not count toward time-to-first-crash.
- ~~FR-2 returns coverage, but INDEX lists no dependency on AFL-002. Should the
  executor call coverage.py, or return raw data for the caller to interpret?~~
  **Resolved (human, 2026-11-07):** the executor owns a `coverage.ShmBitmap` and
  returns interpreted edges. `depends_on: [AFL-002]`.
- ~~FR-6 lists `executor.py` as a module for "crashing inputs saved with signal +
  faulting context". This ticket covers classification only. Saving is in
  AFL-013. Confirm that split.~~
  **Resolved (human, 2026-11-07):** the executor only classifies and captures
  stderr. AFL-007 saves crashes and AFL-013 dedups them.
- ~~FR-2 says "stdin/file input". Must both modes be supported, or is either one
  enough? Both current targets read stdin.~~
  **Resolved (human, 2026-11-07):** stdin only. Add a file mode when a target
  needs one.

## Acceptance criteria
- [x] Executes the target binary on one given input, delivered via stdin. The
      target path is resolved to an absolute path, and the target runs with
      `shell=False`.
- [x] Enforces a timeout (default 1.0 s, constructor parameter `timeout_s`). A
      target that runs past the limit is killed, and `run()` returns within
      `timeout_s` + 1 s.
- [x] Returns an `ExecResult` with exit status, terminating signal, edges, exec time
      and stderr for every run. `edges` is the set of hit edges (empty on timeout).
- [x] **Three outcomes.** `ExecResult.outcome` returns exactly one of `"clean"`,
      `"crash"`, `"hang"` for every run, and `crashed` is `outcome == "crash"`.
      Precedence: `"hang"` iff the timeout fired; otherwise `"crash"` iff the
      terminating signal is SIGSEGV or SIGABRT; otherwise `"clean"`. A clean run
      may have a non-zero exit code; that code is still recorded in `exit_status`.
- [x] Timeout ⇒ `outcome == "hang"`, `crashed is False`, `edges == frozenset()`.
      A hang is never classified as crash or clean.
- [x] A run terminated by SIGSEGV or SIGABRT ⇒ `outcome == "crash"`.
- [x] A run that exits normally with no signal ⇒ `outcome == "clean"` and
      `crashed is False`.
- [x] **ASan (ADR-0002).** An ASan-detected memory error ⇒ `outcome == "crash"`
      (SIGABRT), with the ASan report in `stderr`. This still holds when the parent
      process environment has `ASAN_OPTIONS=abort_on_error=0:detect_leaks=1`. The
      child always sees exactly `abort_on_error=1:detect_leaks=0:symbolize=1`.
      All other inherited environment variables reach the child.
- [x] One `ShmBitmap` is reused across runs and reset before each run. Two
      consecutive runs on different inputs return each run's own edges, with no
      stale edges from the previous run. `close()` releases and unlinks the
      bitmap even if a run raised. It is safe to call twice.
- [x] `targets/cov_rt.c` fails loudly: if `FUZZ_SHM_NAME` is set but the
      `shm_open` or `mmap` fails, it writes a message to stderr and exits with a
      non-zero status (not via a signal, so it is not misread as a crash). It
      must not run silently uninstrumented.
- [x] Runs only local binaries passed in by the caller. It makes no network calls
      (NFR-6).
- [x] Throughput is measured on a toy target, using the `-O0` ASan build from
      `make -C targets`, and reported against the AFL-001 baseline of ~24
      execs/sec (fresh ASan process + fresh shm per exec). Either outcome passes:
      (a) measured throughput meets NFR-3 (≥500 execs/sec on a laptop); or (b) it
      falls short, and the shortfall, the executor bottleneck, and its
      campaign-budget impact (AFL-011 trial counts/durations) are documented as a
      threat to validity per NFR-3. The outcome is recorded in this ticket's log.

## Technical notes (architect)
- **Interfaces (`executor.py`).** This is the FR-2 contract. Corpus, fuzzer and dedup
  all consume `ExecResult` and nothing else:
  ```python
  Outcome = Literal["clean", "crash", "hang"]
  CRASH_SIGNALS = frozenset({signal.SIGSEGV, signal.SIGABRT})
  ASAN_OPTIONS = "abort_on_error=1:detect_leaks=0:symbolize=1"  # ADR-0002

  @dataclass(frozen=True)
  class ExecResult:
      exit_status: int | None   # None if killed by a signal or timed out
      signal: int | None        # terminating signal; None on timeout (our kill)
      timed_out: bool
      edges: frozenset[int]     # empty if timed_out
      exec_time: float          # wall-clock seconds for this run
      stderr: bytes             # ASan report; consumed by dedup (AFL-013)
      @property
      def outcome(self) -> Outcome: ...  # hang > crash > clean, see AC
      @property
      def crashed(self) -> bool: ...     # outcome == "crash"

  class Executor:
      def __init__(self, target: Path, timeout_s: float = 1.0) -> None: ...
      def run(self, data: bytes) -> ExecResult: ...
      def close(self) -> None: ...      # idempotent; unlinks the shm
  ```
- Implementation: `subprocess.run([abs_target], input=data, stdout=DEVNULL,
  stderr=PIPE, timeout=timeout_s, env=env)` with `shell=False`. A negative
  returncode gives the signal. Build `env` once in `__init__`:
  `{**os.environ, "ASAN_OPTIONS": ASAN_OPTIONS, **bitmap.env()}`. Our values come
  last and replace inherited ones (ADR-0002, Option 3). On `TimeoutExpired`, the
  child is already killed. Return `timed_out=True`, `signal=None`,
  `exit_status=None`, empty edges, and whatever stderr was captured.
- `close()`: wrap the bitmap teardown in `try/finally`. A second call is a no-op.
  `ShmBitmap.close()` itself is not idempotent and skips unlink if `shm.close()`
  raises (AFL-002 review). Either guard it in the executor or make `ShmBitmap.close()`
  idempotent. The second touches coverage.py, which is an allowed minimal change.
- **Throughput (human decision, 2026-11-07): outcome (b) expected.** Reuse one
  bitmap (reset per run), keep one process per exec, measure on the `-O0` ASan
  build, and document the shortfall as a threat to validity. Human arithmetic:
  ~20 execs/s → a 10-min trial ≈ 12k execs; 10 trials × 3 targets × 2 schedules
  ≈ 60 trials ≈ 10 h wall-clock (feasible overnight). The AFL-011 pilot adds
  3 × 3 × 2 = 18 trials ≈ 3 h. **A fork server is NOT committed.** It is a
  conditional follow-up, built only if the documented throughput makes AFL-011
  campaigns infeasible in the time available. That is decided at AFL-011 with
  real numbers, as a new ticket. Both arms would get it, so NFR-2 is unaffected.
- **Hangs and metrics.** Hangs are counted (`hangs` column, AFL-007) but are not
  crashes, are not saved as crashes, and never count toward time-to-first-crash
  (AFL-011).
- No RNG and no knowledge of the schedule. Runs only the `target` path it is given,
  makes no network calls (NFR-6).
- **`coverage.run_with_coverage`** (replaces the whole env, sets no
  `ASAN_OPTIONS`): keep it unchanged as the AFL-002 test/spike helper. It is used
  only by `tests/test_coverage*.py` for edge sets, never for classification. Do
  not rebuild it on `Executor`. Fuzzer code must use `Executor`.
- **cov_rt.c fail-loud:** on `shm_open`/`mmap` failure with `FUZZ_SHM_NAME` set,
  `fprintf(stderr, ...)` then `_exit(<distinctive non-zero, e.g. 86>)`. Do not
  `abort()`, because that would be classified as a crash. The runtime stays a
  no-op when `FUZZ_SHM_NAME` is unset.
- **needs_clang alignment** (in scope, test hygiene): the `skipif` in
  `tests/test_coverage.py` checks `clang` on PATH, but the Makefile prefers
  `/opt/homebrew/opt/llvm/bin/clang`. Use one shared check: skip unless either
  that clang or `clang` on PATH exists. Reuse it for the executor integration tests.

## Test approach (tester)
Unit/integration tests with small helper targets that exit cleanly, exit non-zero,
segfault, abort and hang. Assert the `outcome` for each, that exactly one outcome
holds per run, and that the timeout fires within `timeout_s` + 1 s. ASan: run a
built target's ASan trigger (toy_parser `BUG`, or tlv_parser once AFL-010 lands)
with `ASAN_OPTIONS=abort_on_error=0:detect_leaks=1` exported in the test process.
Assert `outcome == "crash"` and `AddressSanitizer` in stderr. Assert the child
sees the forced `ASAN_OPTIONS`, e.g. with a helper that prints its env to stderr.
Bitmap reuse: run A then B then A on toy_parser and assert the edge sets equal
fresh single runs. Throughput: time ≥1000 execs of a benign toy input.

## Log
- 2026-11-07 — created (req-engineer)
- 2026-11-07 — AC added from AFL-001 spike (ADR-0001)
- 2026-11-07 — technical note reconciled with throughput AC (decision rule)
- 2026-11-07 — open questions resolved per human decisions (architect): ADR-0002
  written and accepted (ASan options replace any inherited value); 3-outcome model
  (clean/crash/hang) with ACs; AC1 fixed to stdin; AC3 "(empty on timeout)" fixed;
  depends_on AFL-002; throughput outcome (b) expected, fork server conditional on
  AFL-011; no-instrumentation guard moved to AFL-007; cov_rt fail-loud and
  needs_clang alignment kept in scope; AFL-011 note on TTFC vs hangs added
- 2026-11-07 — DoR verified; moved to in-progress (crew-lead)
- 2026-11-07 — reviewed: all 12 ACs verified, approved; moved to testing (reviewer)
- 2026-11-07 — tested: PASS on clean copy; 2 tests added; status ready to close (tester)
- 2026-11-07 — closed (crew-lead): DoD verified — 12/12 ACs evidenced, ADR-0002 present and referenced, ruff/mypy clean, pytest 20 passed

## Notes from AFL-002 review/test
Follow-ups (not ACs; address while implementing):
- `ShmBitmap.close()` is not idempotent, and unlink is skipped if `shm.close()` raises. The executor owns the bitmap: wrap its lifetime in `try/finally`. (→ now an AC)
- ~~Fail fast if the first seed yields an empty edge set (AFL's "no instrumentation detected"), e.g. a target built without trace-pc-guard.~~ → moved to AFL-007.
- Measure NFR-3 throughput on the actual `-O0` ASan build (ADR-0001), not an optimised one. (→ in throughput AC)
- Test `ShmBitmap.reset()` and bitmap reuse across consecutive runs (no stale edges). (→ now an AC)
- `needs_clang` skipif in tests checks `clang` on PATH, not the Homebrew clang the Makefile prefers; align it. (→ technical notes, in scope)
- ~~Pass `ASAN_OPTIONS` over the inherited env (as in the ASan note above) rather than stripping the env.~~ → superseded by ADR-0002: keep the inherited env, but replace `ASAN_OPTIONS` outright (now an AC).
- Resolve the target binary to an absolute path before exec. (→ in AC1)
- `cov_rt.c` should fail loudly (non-zero exit / stderr) if `shm_open` fails while `FUZZ_SHM_NAME` is set, instead of silently running uninstrumented. (→ now an AC)
- 2026-11-07 — implemented (developer). executor.py (ExecResult/Executor), ShmBitmap.close() idempotent
  (unlink in finally), cov_rt.c fail-loud (_exit(86)), tests/conftest.py shared needs_clang,
  tests/test_executor.py. All 12 ACs verified by tests; ruff/mypy/pytest pass.
- 2026-11-07 — THROUGHPUT (outcome b): 200 runs of toy_parser "A" (-O0 ASan build, one Executor,
  bitmap reused) = 23.4 execs/s (42.7 ms/exec) vs NFR-3 target 500 and AFL-001 baseline ~24.
  Bottleneck: fresh ASan process startup per exec (not shm; reuse gave no gain). Campaign impact:
  ~23 execs/s => 10-min trial ~14k execs; 2 targets x 2 schedules x 10 trials = 40 trials ~ 6.7 h
  + ~3 h pilot. Threat to validity per NFR-3. No fork server built (conditional, decided at AFL-011).

## Review (reviewer, 2026-11-07) — APPROVED → testing
Gates: `make -B -C targets`, ruff, mypy, pytest (17 passed, executor.py 100% line cov) all green.
Independently verified (ad-hoc script, outside sandbox, parent env
`ASAN_OPTIONS=abort_on_error=0:detect_leaks=1:log_path=...`): child env has exactly the
ADR-0002 string, PATH inherited, no asan log file written, toy `BUG` -> crash/SIGABRT with
ASan report in stderr; A/B/A/BUG/A edges equal fresh-Executor edges; run() raising
(missing binary) then close() x2 -> segment unlinked; standalone (FUZZ_SHM_NAME unset) rc 0;
throughput 1000 execs of "A" = 20.9 execs/s (consistent with dev's 23.4/200).
Mutation check: hang-precedence removal, env-order swap, dropped reset(), widened
CRASH_SIGNALS, non-idempotent close each fail >=1 test.
Correction to dev throughput log: campaign impact used 2 targets (current main.yaml);
PRD §8 requires >=3 targets -> 60 trials ~ 10-12 h + 18-trial pilot ~ 3-3.5 h at ~21-23 execs/s
(matches the architect's arithmetic). AFL-011 should plan on the 3-target figure.
Non-blocking (later tickets / tester):
- Timeout kills only the direct child (subprocess.run); grandchildren are orphaned (verified
  with a sh script). Fine for our single-process C targets; revisit only if a target forks.
- No test asserts `stderr == b""`/bytes on hang (the `or b""` guard survives mutation); no
  automated test for close-after-run-raised (verified by hand). Tester may add both.
- On Darwin ASan aborts by default, so the ASan-env test alone does not discriminate there;
  the env-echo test is what pins ADR-0002 on macOS. Linux run would make the ASan test bite.
- ADR-0002 requires recording ASAN_OPTIONS in each trial's run.json -> AFL-011.
- `test_cov_rt_failure_is_clean_via_executor` pokes `ex._env` (private); acceptable in tests.

## Test (tester, 2026-11-07) — PASS → ready to close
- Clean copy (no .git/.venv/.claude/targets/bin/results/caches), `make -C targets` from scratch
  (Homebrew clang, -O0 ASan), repo .venv: ruff clean, mypy clean, pytest 17 passed x3, 100% cov.
- Reviewer gaps filled in tests/test_executor.py: `test_hang_stderr_is_bytes` (b"" when nothing
  captured, b"hi\n" when captured) and `test_close_after_run_raised_unlinks`. Mutations (temp copy
  only): dropping `or b""` on hang -> fails; non-idempotent ShmBitmap.close -> fails; skipping
  unlink -> fails. Real repo after adding: ruff/mypy clean, pytest 20 passed x3; hang tests 20x, 0 flakes.
- Spot checks (outside sandbox, parent ASAN_OPTIONS=abort_on_error=0:detect_leaks=1:log_path=<tmp>):
  child env = ADR-0002 string; toy BUG -> crash/SIGABRT, ASan report in stderr, no log file
  written; exactly one outcome over 11 mixed runs (clean/nonzero/SEGV/ABRT/TERM/hang/ASan);
  reused-bitmap edges == fresh-Executor edges over A,B,BUG,A,"",B; bogus FUZZ_SHM_NAME -> rc 86,
  "cov_rt: cannot attach shm", no signal; throughput 200 x "A" = 21.9 execs/s (within 20.9-23.4).
- Experiment validity: determinism 10 repeats x 4 inputs -> identical (edges, outcome, signal,
  exit); Executor(target, timeout_s) has no schedule/RNG input, env built once in __init__, so both
  arms get an identical executor; ASAN_OPTIONS is a fixed module constant (recordable in run.json,
  AFL-011). Throughput outcome (b) confirmed; plan AFL-011 on the 3-target figure (reviewer note).
