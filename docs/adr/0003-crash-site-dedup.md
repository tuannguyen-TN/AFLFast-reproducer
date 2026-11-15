# ADR-0003: Crash de-duplication by first in-target frame

- **Status:** accepted
- **Date:** 2026-11-14
- **Owner:** architect
- **Related:** AFL-013, AFL-007, FR-6, PRD section 8, ADR-0005 section 3

## Context
FR-6 says dedup buckets by "crash site (PC / top-of-stack hash)" but gives no
stack depth and no source of the faulting context. Klees et al. show that
stack-based dedup misstates bug counts, so the heuristic must be fixed, named and
its biases stated.

## Options considered
1. Faulting PC alone — varies with ASLR and build, not replay-safe.
2. Hash of the top N frames — needs an arbitrary N; overcounts one bug reached
   from several call stacks.
3. First in-target stack frame (function name) — stable across processes, one
   key per planted bug when each bug sits in its own function.

## Decision
- **"PC / top-of-stack" means the first in-target stack frame**: the function of
  the first frame of the first ASan stack whose source file is the target's. It is
  computed once, by AFL-007's shared extractor `fuzzer.fuzzer.crash_site`, and
  stored in the `crash_site` column of `crash_events.csv`.
- **The key is the site only.** The signal is not part of it; no top-N hash.
- **Source is the event stream.** `harness/dedup.py::bucket_trial` buckets every
  row of `crash_events.csv`. Saved inputs (`saved` column) are only replay
  examples, never counted. dedup.py has no frame-parsing code, so event-stream
  time-to-first-crash and dedup counts agree on the site.
- **Placement.** dedup runs offline in `harness/`; the harness may import the
  fuzzer, never the reverse. The executor classifies, the fuzzer extracts and
  saves, dedup buckets.
- **Sentinels.** `"no_stack"`, `"unsymbolized"`, `"no_target_frame"` each get
  their own bucket with `bug_id=None`, reported as unknown crashes, never merged
  with a real-site bucket or each other.
- **Ground-truth mapping.** A real-site bucket maps to bug B when the site equals
  B's `function` in `targets/ground_truth.json` (looked up only among the trial's
  target's bugs; `target` is required, and a target with no entry raises). Everything else is `bug_id=None`. Per-bug TTFC = minimum
  `first_elapsed_s` over that bug's buckets.
- **`crash_site` is process-invariant (binding; enforces ADR-0005 section 3,
  "`crash_site` is replay-safe").** The format contains no absolute address, no
  PID and no path, so identical crashes in different processes give the same
  string. Any change to the extractor or this key must keep it free of
  process-varying content, or exec-index replay breaks. Tested on toy-2's
  trigger `b"!aaa"` run in two separate processes.
- **A missing symbolizer gives `no_target_frame` (moved here from ADR-0005
  section 3).** `crash_site()` returns `"unsymbolized"` only when no frame of the
  first stack has a function name. When some frames have names but none is in the
  target's source file, it returns `"no_target_frame"`. Without a working
  symbolizer the ASan runtime and system-library frames can still have names, but
  the target's frames have no `file:line`; that report is labelled
  `"no_target_frame"`, not `"unsymbolized"`. A target built without `-g` gets the
  same label: `-g` is in the Makefile's overridable `CFLAGS`, not in
  `REQUIRED_FLAGS`. So `"no_target_frame"` does not tell "symbolization failed" apart
  from "crashed outside the target". AFL-011's pre-flight symbolizer check covers
  this: one known trigger per planted bug must make `crash_site()` return that
  bug's `function`, or the campaign aborts.

## Consequences
- Known biases, disclosed in the `dedup.py` docstring: one bug reached via
  several sites overcounts; two bugs in one function merge (hence one planted bug
  per function). For planted bugs the ground-truth mapping is the honest count.
- Sentinel buckets inflate the unique-crash count if symbolization breaks;
  AFL-012 flags nonzero sentinel counts.
- Interface for AFL-012/AFL-014: `bucket_trial(trial_dir, target)` (AFL-012/014 pass the trial's target); unique
  crashes = `len(buckets)`.

## Stackless crashes merge under `no_stack` (AFL-030, option A: disclosed bias)
Decided option A (human decision, 2026-11-14). `crash_site()` and dedup are
unchanged. Disclosure:
1. Every crash with no ASan stack shares the bucket `"no_stack"`, whatever its
   signal (SIGILL, SIGTRAP, SIGABRT when not caused by an ASan report, SIGKILL,
   SIGTERM, SIGINT, ...).
2. Such a bucket never maps to a planted bug (`bug_id=None`).
3. Under AFL-007's storage rule (`_Recorder.crash`) an input is saved only when its
   `path_id` has not been seen in any earlier crash or its `crash_site` has not
   been seen. Once `"no_stack"` has been seen, a stackless crash on an already
   seen `path_id` is not saved, whatever its signal. Every event row in `crash_events.csv` keeps its signal, so crash counts
   are unaffected; only replay inputs are lost.
4. Accepted because no planted target can raise a stackless crash. This is
   enforced by `tests/test_target_static_check.py`, which globs `targets/*.c`,
   strips C comments and must fail on `abort(`, `raise(`, `kill(`, `signal(`,
   `sigaction`, `pthread_kill`, `assert(`, `__builtin_trap`,
   `__builtin_unreachable`, `__builtin_abort`, `__builtin_debugtrap`,
   `__builtin_verbose_trap`, `asm` / `__asm` / `__asm__`, `alarm(`, `ualarm(`,
   `setitimer(`, `setrlimit(`, `killpg(`, `syscall(` (`__asm`, `ualarm(` and
   `syscall(` added, lead decision, 2026-11-15). See AFL-030's analysis. A `no_stack` event therefore
   comes from outside the planted bugs.
5. Empirical record (one-off, real `Executor`, campaign flags and forced
   `ASAN_OPTIONS`, 3 runs per mode, consistent; AFL-030 "Condition-1 evidence"
   notes). clang: Homebrew clang 23.1.3. macOS: 26.5 (25F71), arm64. The runtime
   defaults were read with `ASAN_OPTIONS=help=1` on 2026-11-14; ADR-0002 sets no
   `handle_*` option, so they apply: `handle_segv=1`,
   `handle_sigbus=1`, `handle_sigfpe=1`, `handle_abort=0`, `handle_sigill=0`,
   `handle_sigtrap=0`.

   | Mode | Signal received | ASan report with stack | `crash_site` |
   |---|---|---|---|
   | `raise(SIGILL)` | SIGILL | no | `"no_stack"` |
   | `__builtin_trap()` | SIGTRAP (`brk #1`, not SIGILL) | no | `"no_stack"` |
   | `raise(SIGBUS)` | SIGABRT | yes (BUS report) | the function |
   | real SIGBUS (truncated mmap'd file touched) | SIGABRT | yes (BUS report) | the function |
   | `raise(SIGFPE)` | SIGABRT | yes (FPE report) | the function |
   | real integer divide by zero | none: clean exit (`sdiv` gives 0 on arm64) | n/a | n/a (not a crash) |
   | `abort()` | SIGABRT | no | `"no_stack"` |
   | `__builtin_unreachable()` reached at `-O0` | SIGTRAP | no | `"no_stack"` |
   | null write | SIGABRT | yes (SEGV report) | the function |
   | `raise(SIGSEGV)` | SIGABRT | yes | the function |
   | failing `assert()` | SIGABRT | no (libc text only) | `"no_stack"` |
   | `signal(SIGSEGV, SIG_DFL)` then a null write | SIGSEGV (raw) | no (ASan handler replaced) | `"no_stack"` |

   The record does not decide between A and B; A rests on the static check.
6. Signals not raised by the target, e.g. an OS SIGKILL under memory pressure
   with parallel trials, or Ctrl-C's SIGINT (AFL-018 N1), show up exactly as
   `no_stack` crashes.
7. They add to crash events (`crash_events.csv` rows) and to the exploratory
   unique-crash counts (PRD section 8(b)).
8. They cannot be attributed to a planted bug, so they cannot change the primary
   endpoints (time-to-first-crash for the deep bugs, final edges; AFL-012) by
   being counted. An outside SIGKILL does change the affected trial's path
   (that execution ends early and is recorded as a crash), so that trial's endpoints are affected.
- **Tripwire.** The final report (AFL-025) gives the number of
  `crash_events.csv` rows with `crash_site == "no_stack"` per target and arm; a
  non-zero count is discussed as a threat to validity.
- **Pre-registered contingency.** If the pilot (AFL-011's first or confirmation
  pilot) shows any `no_stack` crash on any target in either arm, the human
  reconsiders option B (signal in the sentinel) before the AFL-011 freeze, and the
  outcome is logged in AFL-030. The pilot count comes directly from
  `crash_events.csv` rows with `crash_site == "no_stack"`, per target and arm.
