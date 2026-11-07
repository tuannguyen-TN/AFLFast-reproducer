# ADR-0002: AddressSanitizer runtime configuration

- **Status:** accepted (human decision, 2026-11-07)
- **Date:** 2026-11-07
- **Owner:** architect
- **Related:** AFL-003, AFL-010, AFL-011, AFL-013, FR-2, FR-6, NFR-1, NFR-2, NFR-4, SC1

## Context
FR-2 counts a run as a crash only if it is killed by SIGSEGV or SIGABRT. Our
targets are built with ASan (ADR-0001, non-overridable `REQUIRED_FLAGS`). ASan's
default on an error is platform-dependent: on Linux it prints a report and calls
`_exit(1)` (`abort_on_error=0`); on Darwin it aborts by default. With the Linux
default, an ASan finding exits with status 1 and no signal. The crash metric would
then silently miss real bugs, and the miss would differ between our macOS dev box
and Linux (NFR-4).

This matters most for tlv_parser (AFL-010). Its overflow is value-triggered
(length byte in the guarded range), not reached via a new branch, so coverage
will not lead the fuzzer to it. An out-of-bounds stack write
usually does not segfault on its own, so the ASan abort is the only thing that
makes it a countable crash.

toy_parser has the same exposure. Its null dereference on `BUG` is caught
by ASan's SEGV handler, which reports `AddressSanitizer: SEGV`. On Linux the
handler then exits 1, so the process never dies by SIGSEGV. AFL-002 saw rc 134
(SIGABRT) only because the dev box runs Darwin.

The environment can also override ASan. A user's shell or CI may export
`ASAN_OPTIONS` (e.g. `abort_on_error=0`, `detect_leaks=1`, `log_path=...`). This
is the same failure class as the `CFLAGS` bug fixed in AFL-002: an inherited
setting silently disables something the experiment depends on.

## Options considered
1. **Leave ASan defaults; widen FR-2** to "non-zero exit + ASan report on stderr = crash".
   Con: needs a PRD change, parses stderr to classify, and is platform-dependent.
2. **Set the required options, append after any inherited `ASAN_OPTIONS`**
   (`f"{inherited}:{required}"`; ASan parses left to right, so later wins). Pro: user
   extras survive. Con: inherited options we do *not* force still apply. For example,
   `log_path=` sends the report to a file, so stderr is empty and dedup (AFL-013) loses
   it. `handle_segv=0` and `allocator_may_return_null=1` change what crashes. Results
   then depend on the operator's shell, which breaks NFR-1.
3. **Replace `ASAN_OPTIONS` outright** with one fixed string. All other inherited
   env vars are kept.

## Decision
**Option 3.** For every run, the executor (AFL-003) sets exactly:

```
ASAN_OPTIONS=abort_on_error=1:detect_leaks=0:symbolize=1
```

It replaces any inherited value. The rest of the inherited environment passes
through unchanged (PATH, `ASAN_SYMBOLIZER_PATH`, etc.). `FUZZ_SHM_NAME` comes from
the executor's `ShmBitmap`. The string is a module constant in `executor.py`
and is recorded in each trial's `run.json` (NFR-1).

Why replace rather than append: appending forces the three options we name but
lets every other inherited option through, and some of those (`log_path`,
`handle_segv`, `exitcode`, `halt_on_error`, ...) silently change what counts as a
crash or what dedup sees. Replacing makes the target's ASan behaviour a function
of the code alone, identical on both arms (NFR-2) and both platforms (NFR-4).
The cost is that you cannot add a debug option from the shell. To debug, run
the binary by hand. No scheduled or recorded run is affected.

- `abort_on_error=1`: every ASan finding, including an ASan-intercepted SEGV,
  ends in `abort()` and therefore SIGABRT. That is a crash under FR-2 as written,
  so no PRD change is needed.
- `detect_leaks=0`: on a leak, LeakSanitizer exits non-zero at process exit. A
  leak is not a memory-safety crash, and LSan is unsupported on macOS. Keeping it
  on would make the outcome differ between platforms.
- `symbolize=1`: the stderr report carries function/file:line frames that
  dedup (AFL-013) buckets on. This costs time only on crashing runs. On Linux it
  needs `llvm-symbolizer` on PATH or `ASAN_SYMBOLIZER_PATH`, which are inherited.

## What AFL-010 relies on (the "agreed ASan configuration")
Under this ADR, the tlv_parser trigger run through the executor gives:
`signal == SIGABRT`, `exit_status is None`, `outcome == "crash"`,
`crashed is True`, and `stderr` containing `ERROR: AddressSanitizer:
stack-buffer-overflow` with a WRITE frame in the memcpy interceptor followed by
`main tlv_parser.c:<memcpy line>`. A benign input gives `outcome == "clean"`,
`exit_status == 0`, and no `AddressSanitizer` in stderr. This holds even when the
parent process exports `ASAN_OPTIONS=abort_on_error=0` (tested in AFL-003).

## Consequences
- Every ASan-detected memory error is a countable crash on both platforms. SC1 and
  time-to-first-crash (AFL-011) are measurable for tlv_parser.
- FR-2's crash rule stays as written (SIGSEGV/SIGABRT). Other signals (SIGBUS,
  SIGILL, SIGFPE) are not crashes under FR-2. Our targets do not raise them.
  Widening the rule needs a PRD ticket.
- Hangs (timeout) are a separate outcome, never a crash (AFL-003).
- Abort plus symbolization makes each crashing run slower. Crashes are rare
  relative to execs, so the effect on NFR-3 throughput is negligible. AFL-007's
  crash-storage filter limits the disk cost.
- **Threat to validity / deviation:** afl-fuzz also forces `abort_on_error=1` and
  `detect_leaks=0` for ASan targets, but runs with `symbolize=0`, and it rejects a
  user `ASAN_OPTIONS` that lacks `abort_on_error=1` instead of replacing it.
  AFLFast's subjects were mostly not ASan builds. Our crash set is "ASan-detected or signal", which is
  stricter than plain AFL's signal-only crashes. Both arms share it, so NFR-2 holds.
  Disclose this in the report.
- The test helper `coverage.run_with_coverage` (AFL-002) replaces the whole env
  and does not set `ASAN_OPTIONS`. It is used only by coverage tests for edge sets,
  never for crash classification. All fuzzing and classification goes through
  `Executor`.
