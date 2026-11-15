---
id: AFL-030
title: Stackless crashes from different signals merge under `no_stack`
requirement: FR-6 / NFR-1 (honesty of reported results); PRD §8 (crash de-duplication, threats to validity)
paper_ref: Klees § performance measures (crash de-duplication over/undercounts; ground truth); AFL whitepaper (any fatal signal is a crash, adopted by AFL-018)
module: option A: docs/adr/0003-*.md, tests/ (static target check); option B: src/fuzzer/fuzzer.py, tests/test_fuzzer.py, tests/ (dedup), docs/adr/0005-stopping-and-exec-index-replay.md §3, docs/adr/0003-*.md
depends_on: [AFL-007, AFL-013, AFL-018]
status: backlog
owner: developer (ADR text left uncommitted for the human to read as a diff)
---

## Goal
After AFL-018, a run ended by any terminating signal is a crash, except our own
timeout kill. AFL-013 buckets crashes by `crash_site` only, not by signal. A crash
with no ASan stack gets the sentinel `"no_stack"` from AFL-007's `crash_site()`
(`src/fuzzer/fuzzer.py`). So stackless SIGILL, SIGBUS, SIGFPE, SIGTERM and SIGKILL
crashes all merge into one unknown bucket (`bug_id=None`), and none of them can map
to a planted bug. This ticket makes that undercount either a disclosed bias or
removes it, so the unique-crash count (PRD §8(b)) is honest (Klees).

Second effect (AFL-018 review, R2, verified by simulation): AFL-007's crash-input
storage rule (`_Recorder.crash`) saves an input only when its `path_id` is new or
its `crash_site` is new. Stackless crashes of different signals on one `path_id`
therefore share (path_id, `"no_stack"`), and only the first input is saved. Event
rows in `crash_events.csv` still carry each signal, so crash counts are unaffected;
only the replay inputs are lost.

Source: AFL-018 Log (2026-11-14 AFL-013 check) and its Review section, R2.

## Decision for the human
**Decided: option A, with conditions (human decision, 2026-11-14).** The
conditions are the option A ACs below: (1) an empirical ASan record, (2) a strict
static source check, (3) an extended ADR-0003 disclosure, (4) a pre-registered
contingency on the pilot, and landing before the AFL-011 freeze. Option B's ACs
are struck through and kept as history.

Choose exactly one. The choice gates the AFL-011 freeze (see Ordering).

- **(A) Disclosed bias.** If no planted target can raise a stackless crash, record
  the merge as a disclosed bias in ADR-0003 (the dedup ADR written by AFL-013).
  The code does not change.
- **(B) Signal in the sentinel.** The stackless sentinel carries the signal name,
  e.g. `no_stack:SIGILL`, in the `crash_site` written by AFL-007's extractor.
  Dedup stays site-only and verbatim (AFL-013), but different stackless signals
  stay apart, and the storage rule then saves one input per stackless signal. This
  changes `crash_site`, a column the AFL-011 freeze pins, so it must land before
  the AFL-011 freeze.

## Acceptance criteria

### Both options
- [ ] **Analysis recorded before the decision (read-only).** The Technical notes
      first-pass analysis ("Can a planted target raise a stackless crash?") is
      reviewed against the target sources that exist when the human decides, and
      its verdict (yes / no, with confidence and named assumptions) is recorded in
      this ticket's Log. Any planted bug (`toy-1`, `toy-2`, `tlv-1`, `tlv-2`,
      `mfp-1`, `mfp-2`) whose source is not yet written is listed as "covered by
      its ticket's ACs, not by source reading". No build, no run.
- [ ] **Decision recorded.** The Log records the human's choice (A or B) with date.
      Only the chosen option's ACs below apply; the other block is struck through.
- [ ] **Ordering.** The decision is made before the AFL-011 freeze. If B is chosen,
      this ticket lands (committed) before the AFL-011 freeze, because it changes
      `crash_site`.

### Option A: disclosed bias (code unchanged) (chosen, human decision, 2026-11-14)
- [ ] **Premise: the source check, not the analysis verdict alone.** Option A
      rests on the strict static source check below: no target source contains a
      form that ends a run without an ASan report. The recorded analysis verdict
      and the empirical ASan record are supporting evidence, not the gate. The
      empirical record shows that some signals do arrive stackless (SIGILL,
      SIGTRAP, a SIGABRT not caused by ASan, any signal whose ASan handler the
      target replaced; Technical notes, "Condition-1 evidence"). A still holds,
      because the source check keeps every target from raising them. If a target
      cannot pass the source check without changing a planted bug, option A is
      not available for it and the ticket returns to the human.
- [ ] **Empirical ASan record (condition 1; human decision, 2026-11-14).** A
      one-off check on this machine, outside this ticket's implementation, built a
      throwaway program with the campaign's exact flags, ran it through the real
      `Executor` with the forced `ASAN_OPTIONS` (ADR-0002), and raised SIGILL,
      SIGBUS, SIGFPE and the other modes listed in Technical notes,
      "Condition-1 evidence" (done 2026-11-14; results recorded there).
      ADR-0003's disclosure records, per signal or mode, the signal received and
      whether an ASan report with a stack was produced (`crash_site` a function
      or `"no_stack"`), with the clang version (Homebrew clang 23.1.3) and the
      macOS version (macOS 26.5 (25F71), arm64). The result is a record; it does
      not decide between A and B. A rests on the source check. Test: review/grep
      check of ADR-0003 for one entry per mode in the evidence table and both
      versions.
- [ ] **Strict static source check (condition 2; human decision, 2026-11-14).**
      A pytest test globs `targets/*.c` when it runs, so it covers every target
      source, including `tlv-2` (AFL-010) and the mini-format bugs `mfp-1`,
      `mfp-2` (AFL-016) once they are written, not a fixed file list. It strips C
      comments (`/* ... */` and `// ...`) from each file, then fails, naming the
      file and the form, if any of these forms appears as a call or a use:
      - `abort(`, `raise(`, `kill(`, `signal(`, `sigaction`, `pthread_kill`;
      - `assert(`. Rationale: a failed assert calls `abort()`, and unless ASan
        handles SIGABRT (it does not by default, `handle_abort=0`), that ends
        with no ASan report, i.e. a `no_stack` crash;
      - `__builtin_trap`, `__builtin_unreachable`, `__builtin_abort`,
        `__builtin_debugtrap`;
      - `__builtin_verbose_trap`, `asm` / `__asm__`, `alarm(`, `setitimer(`,
        `setrlimit(`, `killpg(` (orchestrator addition from the condition-1
        evidence, 2026-11-14; human to confirm at the staged diff). Same
        category: calls and compiler built-ins that end a run without a report.

      Names match on identifier boundaries. `\babort` does not match
      `__builtin_abort` (`_` is an identifier character), so both are listed
      and checked separately. `static_assert` must not match `assert(`. It passes
      on the current tree. Comment stripping is required: `targets/cov_rt.c:33`
      ("via a signal (would") and `targets/toy_parser.c:33` ("no signal,
      silent") match the bare words only inside comments. Mutation checks:
      injecting each of `abort();`, `assert(0);` and `__builtin_trap();` into a
      copy of a target source (one at a time, in a temporary directory, never in
      `targets/`) makes the test fail, three separate cases. A further case
      shows `static_assert(1, "x");` alone does not fail it.
- [ ] **ADR-0003 discloses the merge (condition 3; human decision, 2026-11-14).**
      `docs/adr/0003-*.md` states, in a Consequences or threats-to-validity item:
      (1) all crashes with no ASan stack share the bucket `"no_stack"` whatever
      their signal; (2) such a bucket never maps to a planted bug; (3) under
      AFL-007's storage rule only the first stackless input per `path_id` is
      saved, while every event row keeps its signal, so crash counts are
      unaffected; (4) the reason it is accepted: no planted target can raise a
      stackless crash, enforced by the static source check (pointer to that test
      and to this ticket's analysis), so a `no_stack` event comes from outside
      the planted bugs; (5) the empirical per-signal record (condition 1, with
      the clang and macOS versions); (6) signals not raised by the target, e.g.
      an OS SIGKILL under memory pressure with parallel trials, or Ctrl-C's
      SIGINT (AFL-018 N1), show up exactly as `no_stack` crashes; (7) they add to
      crash events (`crash_events.csv` rows) and to the exploratory unique-crash
      counts (PRD §8(b)); (8) they cannot be attributed to a planted bug, so they
      cannot change the primary endpoints (time-to-first-crash for the deep bugs,
      final edges; AFL-012). Test: review/grep check of ADR-0003 for each of the
      eight points.
- [ ] **Tripwire disclosed.** ADR-0003 states that the final report (AFL-025)
      gives the number of `crash_events.csv` rows with `crash_site == "no_stack"`
      per target and arm, and that a non-zero count is discussed as a threat to
      validity. Test: grep check of ADR-0003.
- [ ] **Pre-registered contingency (condition 4; human decision, 2026-11-14).**
      If the pilot (AFL-011's first pilot or confirmation pilot) shows any crash
      with `crash_site == "no_stack"` on any target, in either arm, option B is
      reconsidered by the human before the AFL-011 freeze, and the outcome is
      logged in this ticket. The monitor exists: AFL-012 already counts and flags
      `no_stack` crashes. Test: the pilot's Log entry records the `no_stack` count
      per target and arm; if any is non-zero, this Log records the human's
      reconsideration dated before the freeze commit.
- [ ] **No code change.** `git diff` shows no change under `src/` for this ticket.
- [ ] **Ordering (human decision, 2026-11-14).** This ticket's implementation
      (the static test and the ADR-0003 text) lands, committed, before the
      AFL-011 freeze. AFL-011's pre-freeze checklist item (a) lists AFL-030.
      Test: `ls tickets/done/` lists AFL-030 before the freeze commit.

### ~~Option B: signal in the sentinel~~ (not chosen; human decision, 2026-11-14; kept as history)
- [ ] ~~**Format.** When the first ASan stack has no frames and the run's signal is
      `s`, the `crash_site` written to `crash_events.csv` and to the
      `crashes/*.json` sidecar is `"no_stack:" + signal.Signals(s).name` (e.g.
      `"no_stack:SIGILL"`). A signal number with no `signal.Signals` member gives
      `"no_stack:SIG<number>"`. Signal names, not numbers, are used because numbers
      differ across platforms (SIGBUS is 7 on Linux, 10 on macOS; NFR-4).
      Test: synthetic `stderr=b""` with SIGILL, SIGTRAP, SIGBUS, SIGFPE, SIGTERM
      and SIGKILL gives six distinct values, each equal to `"no_stack:" + <name>`
      (SIGTRAP added for history from the condition-1 evidence, 2026-11-14).~~
- [ ] ~~**One producer.** The value is produced by AFL-007's shared extractor
      (`fuzzer.fuzzer.crash_site`), not composed separately in the loop or in
      dedup. Existing two-argument calls `crash_site(stderr, source)` (tests,
      AFL-016, AFL-029) keep working and still return the plain `"no_stack"` when no
      signal is passed. Test: the existing `tests/test_fuzzer.py` `crash_site`
      cases pass unchanged; a grep check finds no `"no_stack:"` string literal
      outside `src/fuzzer/fuzzer.py` and tests.~~
- [ ] ~~**Other sites unchanged.** A real site, `"unsymbolized"` and
      `"no_target_frame"` are returned exactly as before, whatever the signal.
      Test: AFL-007's captured tlv_parser fixture report still gives `"main"`;
      the existing `test_crash_site_variants` cases pass with a signal passed.~~
- [ ] ~~**Replay-safe.** The new value contains no PID, no `0x`, no `/` and no
      digits except in the `SIG<number>` fallback, so ADR-0005 §3's
      process-invariance guarantee holds. Test: assertion on the six values above.~~
- [ ] ~~**Storage.** Through `_Recorder.crash`, two stackless crashes on the same
      `path_id` with SIGILL then SIGBUS write two `crashes/*.bin` files and two
      `crash_events.csv` rows; a second SIGILL on that `path_id` writes a row and no
      new file. Test: unit test on `_Recorder` with synthetic `ExecResult`s.~~
- [ ] ~~**Dedup keeps them apart.** `harness/dedup.bucket_trial` on a
      `crash_events.csv` with one `no_stack:SIGILL` row and one `no_stack:SIGBUS`
      row gives two buckets, each `bug_id=None`, neither merged with a real-site
      bucket. Test: synthetic CSV. `harness/dedup.py` itself is unchanged (it uses
      `crash_site` verbatim).~~
- [ ] ~~**ADR-0005 §3 amended.** The binding paragraph "`crash_site` is replay-safe"
      says "The signal is not part of it." That line is amended to: the signal is
      not part of a real site, `"unsymbolized"` or `"no_target_frame"`; the
      stackless sentinel carries the signal name (AFL-030). Left uncommitted for
      the human to read as a diff (pre-registration-adjacent).~~
- [ ] ~~**ADR-0003 updated.** ADR-0003's sentinel text names the `no_stack:<SIGNAME>`
      family, states that each signal gets its own unknown bucket, and states the
      residual bias: two stackless crashes with the same signal from different
      causes still merge. Test: review/grep check.~~
- [ ] ~~**AFL-013 consistency.** AFL-013's "Sentinels carried through" AC and its
      tests still pass; any wording change to AFL-013 is made by the req-engineer
      on a human decision and logged there.~~

## Technical notes (architect)

### First-pass analysis: can a planted target raise a stackless crash? (req-engineer, 2026-11-14, read-only)
"Stackless" means `crash_site()` returns `"no_stack"`: stderr contains no line
matching `#<n> 0x<hex> ...`. For a crash (signal set), that happens only when the
process dies by a signal ASan does not handle and print a report for.

ASan runtime defaults (from compiler-rt's `sanitizer_flags.inc`, from knowledge,
not checked in this repo; verify against the installed LLVM): `handle_segv=1`,
`handle_sigbus=1`, `handle_sigfpe=1`, `handle_abort=0`, `handle_sigill=0`.
ADR-0002's fixed `ASAN_OPTIONS` sets none of these, so the defaults apply. So:
- SIGSEGV, SIGBUS, SIGFPE raised by target code: ASan prints a report with a stack,
  then `abort_on_error=1` turns it into SIGABRT. Not stackless. Stack overflow from
  deep recursion is reported as `stack-overflow` with a stack. Not stackless.
- SIGILL (`ud2`/`brk` from `__builtin_trap`, `__builtin_unreachable` in some
  modes), SIGABRT from a target `abort()`/`assert()`, and signals sent from
  outside (SIGTERM, SIGKILL, SIGINT) are not reported. These are stackless.

Per target:
- **toy_parser.c** (`toy-1`, `toy-2`): `toy-1` is a null store in `check()`
  (SIGSEGV, ASan-handled, report with stack, SIGABRT). `toy-2` is a heap over-read
  in `scan()` (ASan report). `main` reads ≤ 256 bytes into a 256-byte buffer. No
  division, recursion, trap, `abort`/`assert`, signal call or stdout write. No
  stackless path.
- **tlv_parser.c** (`tlv-1`, as it exists today): the `memcpy` overflow is caught by
  ASan's `memcpy` interceptor before the write (report with stack). The read side
  `in + 2 .. in + 257` stays inside `in[512]`. `printf` goes to `stdout=DEVNULL`
  (AFL-018 SIGPIPE test), so no SIGPIPE. No stackless path. `tlv-2` is not written
  yet (AFL-010).
- **mini-format** (`mfp-1`, `mfp-2`; AFL-016, not written): AFL-016 requires each
  bug to be an ASan-detectable out-of-bounds access and every crash in the S0
  single-byte sweep to be at a documented site. That sweep covers only the inputs
  it runs, not every fuzzer input, so a stray `assert`/`abort`/trap in the parser
  would be a stackless path the sweep may miss. The option A static test closes
  that gap for every target.
- **cov_rt.c** (linked into every target): on shm attach failure it calls
  `_exit(86)` deliberately ("not via a signal"), which is clean, not a crash.

Verdict: **no**, for toy_parser and tlv_parser as they stand. Confidence: high for
the code paths (both files are small and fully read); medium overall, because the
ASan flag defaults are recalled, not verified against the installed LLVM, and
`tlv-2` and the mini-format do not exist yet (they are covered only by their
tickets' ACs). The only stackless crashes expected in a campaign come from outside
the target (OS memory-pressure SIGKILL, Ctrl-C SIGINT reaching the child; AFL-018
N1). Those are not planted bugs, so merging them is harmless to per-bug TTFC, but
they would be counted as one unknown unique crash.

Corrections from the condition-1 evidence (2026-11-14; the first-pass text above
is kept as written):
- The trap built-ins (`__builtin_trap`, and `__builtin_unreachable` reached at
  `-O0`) give **SIGTRAP** on arm64 (`brk #1`), not SIGILL. Both are still
  stackless (`handle_sigtrap=0`).
- `signal()` / `sigaction` are not on the static-check list just for
  completeness: replacing ASan's handler (e.g. `signal(SIGSEGV, SIG_DFL)`) turns
  a fault ASan would report into a raw, stackless signal.
- A real integer divide by zero does not crash on arm64 (`sdiv` gives 0): the
  run exits clean. The "SIGFPE raised by target code" bullet above applies only
  to an explicit `raise(SIGFPE)`.
- The recalled ASan defaults were checked with `ASAN_OPTIONS=help=1` and are
  correct, plus `handle_sigtrap=0`.

### Condition-1 evidence: empirical ASan record (2026-11-14)
One-off check, outside this ticket's implementation (run by the orchestrator):
a throwaway program built with the campaign's exact flags, run through the real
`Executor` with the forced `ASAN_OPTIONS`, 3 runs per mode, all consistent.
Machine: macOS 26.5 (25F71), arm64; Homebrew clang 23.1.3. Runtime defaults read
with `ASAN_OPTIONS=help=1`: `handle_segv=1`, `handle_sigbus=1`,
`handle_sigfpe=1`, `handle_abort=0`, `handle_sigill=0`, `handle_sigtrap=0`.
ADR-0003's disclosure carries this table with both versions.

| Mode | Signal received | ASan report with stack | `crash_site` |
|---|---|---|---|
| `raise(SIGILL)` | SIGILL | no | `"no_stack"` |
| `__builtin_trap()` | SIGTRAP (`brk #1`, not SIGILL) | no | `"no_stack"` |
| `raise(SIGBUS)` | SIGABRT | yes (BUS report) | the function |
| real SIGBUS (mmap'd file truncated, then touched) | SIGABRT | yes (BUS report) | the function |
| `raise(SIGFPE)` | SIGABRT | yes (FPE report) | the function |
| real integer divide by zero | none: clean exit (`sdiv` gives 0 on arm64) | n/a | n/a (not a crash) |
| `abort()` | SIGABRT | no | `"no_stack"` |
| `__builtin_unreachable()` reached at `-O0` | SIGTRAP | no | `"no_stack"` |
| null write | SIGABRT | yes (SEGV report) | the function |
| `raise(SIGSEGV)` | SIGABRT | yes | the function |
| failing `assert()` | SIGABRT | no (only libc's "Assertion failed" text) | `"no_stack"` |
| `signal(SIGSEGV, SIG_DFL)` then a null write | SIGSEGV (raw) | no: user code replaced ASan's handler | `"no_stack"` |

Stackless, therefore: SIGILL, SIGTRAP, a SIGABRT not caused by ASan, and any
signal whose ASan handler the target has replaced; plus signals from outside
the target (SIGKILL, SIGTERM, SIGINT). The orchestrator's scan of
`targets/*.c` with comments and strings stripped found zero code hits for the
static-check forms; the only bare-word hits are comments (`cov_rt.c:33`,
`toy_parser.c:33`). The targets contain no `/` or `%` arithmetic.

### Design constraint for future targets (2026-11-14, from the condition-1 evidence)
A planted bug must not be an integer divide by zero: it does not trap on arm64,
so it would never be detected as a crash. This applies to `tlv-2` (AFL-010) and
`mfp-1` / `mfp-2` (AFL-016). Already filed there (2026-11-14): it is in the
planted-bug ACs of AFL-010 and AFL-016, and AFL-030 is in AFL-011's pre-freeze
checklist item (a).

### Option B approach (proposal; architect decides)
- Add an optional keyword parameter to `crash_site`, e.g.
  `crash_site(stderr: bytes, source: str, signal: int | None = None) -> str`, used
  only on the no-frames branch. The loop (`fuzzer.py`, the `crash_site(r.stderr,
  source)` call in the crash branch) passes `r.signal`. Two-argument callers are
  unaffected.
- The colon cannot appear in a C identifier, so `no_stack:<NAME>` can never equal a
  `ground_truth.json` `function`; AFL-013's mapping gives `bug_id=None` without a
  special case.
- `SENTINELS` (`fuzzer.py`) has no reader today. If kept, document that the
  stackless sentinel is a prefix family.
- Out of scope: adding the signal to `"unsymbolized"` / `"no_target_frame"`. Those
  have a stack, so the site is the information that is missing, not the signal.

### Ordering
- B changes the `crash_site` column, which AFL-011's freeze pins (ADR-0005 §3
  replay guarantee), and amends binding ADR-0005 §3 text: lands before the freeze.
- A changes no recorded value. Even so, its implementation (static test and
  ADR-0003 disclosure) lands before the AFL-011 freeze (human decision,
  2026-11-14; option A AC "Ordering", AFL-011 checklist item (a)). Superseded:
  "the ADR-0003 disclosure must exist before AFL-025 (results write-up) closes".

## Test approach (tester)
Option A (chosen, human decision, 2026-11-14): grep/review ADR-0003 for the eight
disclosure points, the per-signal empirical record with the clang and macOS
versions, and the tripwire; run the static target test and its mutation checks
(each of `abort();`, `assert(0);` and `__builtin_trap();` added to a scratch copy
of a target must fail it; `static_assert` alone must not); confirm no `src/` diff;
confirm AFL-030 is in `tickets/done/` before the AFL-011 freeze commit; after the
pilot, confirm the contingency was applied if any `no_stack` crash occurred.
Option B: unit tests on `crash_site` (five stackless signals, unknown-number
fallback, unchanged real/sentinel cases, replay-safe format), on `_Recorder.crash`
(one saved input per stackless signal per `path_id`), and on dedup with a synthetic
CSV (two unknown buckets). Confirm ADR-0005 §3 and ADR-0003 agree with the code.
Both: confirm the analysis verdict and the decision are in the Log before the
freeze; `ruff check . && mypy src && pytest`.

## Log
- 2026-11-14 — created (req-engineer)
- 2026-11-14 — decision: option A with conditions (human decision, 2026-11-14)
  (req-engineer). Option B's ACs struck through, kept as history (SIGTRAP added
  to its signal list for history). Option A ACs: "Premise" reworded (A rests on
  the static source check, not on the analysis verdict alone; a stackless
  signal in the empirical record does not void A while the source check keeps
  targets from raising it); new "Empirical ASan record" (condition 1); static
  test made strict (condition 2: glob of `targets/*.c`, comments stripped, forms
  as call or use incl. `assert(` with its rationale and four `__builtin_*`
  forms, three mutation cases); ADR-0003 disclosure widened from four to eight
  points (condition 3); new "Pre-registered contingency" (condition 4: any
  `no_stack` crash in the pilot reopens B before the freeze); tripwire and "No
  code change" kept; new "Ordering" (lands before the AFL-011 freeze, added to
  AFL-011 checklist item (a)). Technical notes Ordering for A updated to match.
- 2026-11-14 — condition-1 evidence folded in (orchestrator's empirical check,
  finished 2026-11-14) (req-engineer): evidence table and machine/version record
  added to Technical notes; first-pass analysis corrected (trap built-ins give
  SIGTRAP on arm64, not SIGILL; `signal()`/`sigaction` make reported faults
  stackless; a real integer divide by zero does not crash on arm64); design
  constraint for future targets (no divide-by-zero planted bug) recorded, to be
  filed in AFL-010 and AFL-016 by the orchestrator; static-check list gained
  `__builtin_verbose_trap`, `asm` / `__asm__`, `alarm(`, `setitimer(`,
  `setrlimit(`, `killpg(` (orchestrator addition from the condition-1 evidence,
  2026-11-14; human to confirm at the staged diff); comment stripping now also
  names `toy_parser.c:33`; `static_assert` must not match.
