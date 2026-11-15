---
id: AFL-030
title: Stackless crashes from different signals merge under `no_stack`
requirement: FR-6 / NFR-1 (honesty of reported results); PRD §8 (crash de-duplication, threats to validity)
paper_ref: Klees § performance measures (crash de-duplication over/undercounts; ground truth); AFL whitepaper (any fatal signal is a crash, adopted by AFL-018)
module: option A: docs/adr/0003-*.md, tests/ (static target check); option B: src/fuzzer/fuzzer.py, tests/test_fuzzer.py, tests/ (dedup), docs/adr/0005-stopping-and-exec-index-replay.md §3, docs/adr/0003-*.md
depends_on: [AFL-007, AFL-013, AFL-018]
status: done
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
- [x] **Analysis recorded before the decision (read-only).** The Technical notes
      first-pass analysis ("Can a planted target raise a stackless crash?") is
      reviewed against the target sources that exist when the human decides, and
      its verdict (yes / no, with confidence and named assumptions) is recorded in
      this ticket's Log. Any planted bug (`toy-1`, `toy-2`, `tlv-1`, `tlv-2`,
      `mfp-1`, `mfp-2`) whose source is not yet written is listed as "covered by
      its ticket's ACs, not by source reading". No build, no run.
- [x] **Decision recorded.** The Log records the human's choice (A or B) with date.
      Only the chosen option's ACs below apply; the other block is struck through.
- [x] **Ordering.** The decision is made before the AFL-011 freeze. If B is chosen,
      this ticket lands (committed) before the AFL-011 freeze, because it changes
      `crash_site`.

### Option A: disclosed bias (code unchanged) (chosen, human decision, 2026-11-14)
- [x] **Premise: the source check, not the analysis verdict alone.** Option A
      rests on the strict static source check below: no target source contains a
      form that ends a run without an ASan report. The recorded analysis verdict
      and the empirical ASan record are supporting evidence, not the gate. The
      empirical record shows that some signals do arrive stackless (SIGILL,
      SIGTRAP, a SIGABRT not caused by ASan, any signal whose ASan handler the
      target replaced; Technical notes, "Condition-1 evidence"). A still holds,
      because the source check keeps every target from raising them. If a target
      cannot pass the source check without changing a planted bug, option A is
      not available for it and the ticket returns to the human.
- [x] **Empirical ASan record (condition 1; human decision, 2026-11-14).** A
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
- [x] **Strict static source check (condition 2; human decision, 2026-11-14).**
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
      - `__asm`, `ualarm(`, `syscall(` (lead decision, 2026-11-15; reviewer
        N2: clang accepts `__asm` as well as `asm` and `__asm__`). Same
        category.

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
- [x] **ADR-0003 discloses the merge (condition 3; human decision, 2026-11-14).**
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
- [x] **Tripwire disclosed.** ADR-0003 states that the final report (AFL-025)
      gives the number of `crash_events.csv` rows with `crash_site == "no_stack"`
      per target and arm, and that a non-zero count is discussed as a threat to
      validity. Test: grep check of ADR-0003.
- [ ] **Pre-registered contingency (condition 4; human decision, 2026-11-14).**
      If the pilot (AFL-011's first pilot or confirmation pilot) shows any crash
      with `crash_site == "no_stack"` on any target, in either arm, option B is
      reconsidered by the human before the AFL-011 freeze, and the outcome is
      logged in this ticket. The count is taken directly from each pilot trial's
      `crash_events.csv`: the number of rows with `crash_site == "no_stack"`, summed
      per target and arm, written by the runner or the pilot evaluation step. It does
      not depend on AFL-012, which excludes pilot results (AFL-011).
      Test: the pilot's Log entry records the `no_stack` count
      per target and arm; if any is non-zero, this Log records the human's
      reconsideration dated before the freeze commit — open by design, evaluated at the
      first pilot; tracked by AFL-011 pre-freeze checklist item (l).
- [x] **No code change.** `git diff` shows no change under `src/` for this ticket.
- [x] **Ordering (human decision, 2026-11-14).** This ticket's implementation
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

## Review (reviewer, 2026-11-15): BOUNCE

Gates: `ruff check .` clean, `mypy src` clean, `pytest tests/test_target_static_check.py
tests/test_dedup.py` 28 passed. An end-to-end probe on a tmp copy of `targets/` with
`abort();` appended to `tlv_parser.c` fails `test_target_has_no_banned_form[tlv_parser.c]`
and names the file and the pattern.

Blocking:
- **B1. Strict static source check: comment stripping has false negatives.** Ticket AC
  "Strict static source check" requires the check to fail when a listed form appears as a
  call. `tests/test_target_static_check.py:25` deletes comments (`""`) and does not skip
  string literals. Probes on `banned_forms()` show three valid C inputs that call `abort()`
  but are not caught:
  - `return/* c */abort();`. The comment is deleted, giving `returnabort`, so there is no
    word boundary. C replaces a comment with one space.
  - `puts("//"); abort();`. `//` inside a string strips the rest of the line.
  - `puts("/*"); abort(); /* x */`. `/*` inside a string swallows up to the next `*/`.
  So "string literals are not stripped" is not only a conservative limit; it can also hide
  a form. Fix: one tokenising regex that keeps string and char literals as they are and
  replaces each comment with a single space, e.g.
  `re.compile(r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|/\*.*?\*/|//[^\n]*', re.DOTALL)`
  with a replacement that returns the literal unchanged and `" "` for a comment. Add the
  three inputs above as failing cases. Verified in a scratch probe: all three are then
  caught, the `static_assert` and comment-only case still passes, and all five current
  `targets/*.c` files still pass. No current target has `//` or `/*` inside a string, so
  the tree is clean today. The bug is in the guard that option A rests on.
- **B2. The contingency bullet in ADR-0003 states something false.**
  `docs/adr/0003-crash-site-dedup.md:121` says "AFL-012 already counts and flags
  `no_stack`". AFL-012 is in `tickets/backlog/`, and `harness/aggregate.py` is a 9-line
  `TODO(AFL-012)` stub. AFL-012 specifies the count (AC "Crash-site sentinel counts") but
  does not implement it, and it does not exist at pilot time. Reword, e.g.: "AFL-012
  specifies a per-trial `no_stack` count and flag (not yet implemented); for the pilot the
  count is taken directly from `crash_events.csv` (rows with `crash_site == "no_stack"`,
  per target and arm)." The same false sentence is in this ticket's "Pre-registered
  contingency" AC ("The monitor exists: ..."). That sentence is req-engineer and human
  text: escalated, not changed by the developer.

Non-blocking (can be done on this bounce, or carried):
- N1. **Duplicate lists.** This ticket's ACs do not require one list. But PRD section 8
  (the "Planted bugs" line), AFL-010 and AFL-016 ("list kept in AFL-030 only") and
  AFL-011 item (k) ("kept there only, not copied here") all say AFL-030 holds the list.
  `tests/test_tlv_parser.py:24` and `tests/test_mini_format.py:38` keep copies, and those
  copies have B1's stripping bug. The defect is in AFL-010 and AFL-016's files, so route it
  there: drop their local loops (this glob test already covers both files) or import this
  list. The docstring at `tests/test_target_static_check.py:6-7` ("the single list ...
  keep their own copies") contradicts itself; reword it once the copies are gone.
- N2. **List gaps.** These are gaps in the ticket's list, not the implementation's. The
  implementation matches the ticket's 18 forms exactly. Not caught: `__asm("brk #1")`
  (clang accepts `asm`, `__asm` and `__asm__`), `ualarm(`, `syscall(`. Recommend the
  req-engineer or human add `__asm` at least, e.g. `\b(?:__)?asm(?:__)?\b`. Also not
  caught, by design: a function-pointer use (`f = abort;`) and macro indirection.
- N3. **ADR point 8 overclaims slightly.** The `no_stack` rows never enter either
  endpoint. But an outside kill (OS SIGKILL) does change the trial: the killed exec's
  coverage and retention are lost, so the trajectory diverges. Suggest a clause: "the rows
  do not enter either endpoint; an outside kill can still perturb the trial itself, which
  the tripwire count discloses."
- N4. **ADR point 1.** "SIGABRT" needs a qualifier, "a SIGABRT not caused by an ASan
  report", because every ASan-reported crash is also SIGABRT under `abort_on_error=1`.
- N5. **ADR point 3.** "Only the first stackless input per `path_id` is saved" is loose.
  The rule saves when `path_id` is new or the site is new, so: at most one, and none if
  that `path_id` already has a saved crash and a `no_stack` input was saved earlier.
- N6. **ADR point 5.** Add how the defaults were read (`ASAN_OPTIONS=help=1`), that
  ADR-0002's forced string sets no `handle_*` flag (so the defaults apply), the date
  (2026-11-14), and a pointer to this ticket's "Condition-1 evidence". The versions were
  confirmed independently on this machine: `sw_vers` gives 26.5 (25F71) and
  `clang --version` gives Homebrew clang 23.1.3. The ASan defaults were not re-run by the
  reviewer.

Per AC:
- **Premise:** met.
- **Empirical record:** met. 12 rows match the evidence table; both versions are given.
- **Static check:** NOT met (B1). List complete against the ticket. `static_assert` and
  `__builtin_abort` boundaries are correct. The file and form are named. The mutation
  cases run on tmp copies (3 forms x 3 campaign targets) plus the `static_assert` case.
  The glob over `targets/*.c` is correct per the AC:
  - `cov_rt.c` is linked into every target, so it must be covered;
  - `spike.c` passes;
  - a future non-target `.c` with a banned form would fail closed;
  - `.h` files are not globbed, and none exist in `targets/`.
- **Disclosure 1-8:** all present, with N3-N5 on precision.
- **Tripwire:** met.
- **No code change:** met. The `src/` diffs belong to AFL-007, AFL-008, AFL-011 and
  AFL-018. `fuzzer.py`'s mtime matches the AFL-011 ticket's, and no AFL-030 trace is in
  `src/` or `harness/`.
- **Contingency:** correctly open (needs the pilot), apart from B2's text.
- **Ordering (A):** correctly open.
- **"Both options":** analysis and decision are recorded in fact (Technical notes; Log
  2026-11-14) but are unticked. The "Analysis" AC asks for the verdict to be in the Log,
  and today it is in Technical notes. This is for the crew lead or req-engineer to tick or
  log, not the developer.

## Re-review (reviewer, 2026-11-15, after bounce 1): APPROVE

Gates: `ruff check .` clean; `mypy src` clean (8 files); `pytest tests/test_target_static_check.py
tests/test_dedup.py tests/test_fuzzer.py --no-cov` 70 passed, 1 deselected (19 of them in the static check).
- **B1 fixed.** `tests/test_target_static_check.py:23-28`: one DOTALL tokenising regex keeps
  string and char literals and replaces each comment with `" "`. New cases at :59-65 pass. A mutation
  check (old delete-comments stripping put back) makes all three return `[]`, so they would fail.
  With no stripping at all, `test_static_assert_and_comments_do_not_fail` fails, so it is not vacuous.
  Further probes:
  - Flagged correctly: `'"'` next to a string, an escaped quote char, a string line-continuation,
    `don't` inside both comment kinds, an `L"/*"` prefix, a `R"(//)"` raw string, a continued `//`
    comment (conservative), `/\<nl>*`, and a C23 digit separator (literals are kept, so a mis-tokenised
    "literal" cannot hide code).
  - Not caught: an identifier split by a backslash-newline (`ab\<nl>ort();`), a `##` token paste,
    and a trigraph `"??/"` followed by `/*` (needs `-trigraphs`, off in clang's gnu modes). None is
    realistic in a planted-bug target, so non-blocking. The function-pointer use and `__asm` are
    already routed (N2).
- **B2 fixed.** `docs/adr/0003-crash-site-dedup.md:125-129` no longer claims that AFL-012 monitors.
  `crash_events.csv` and the `crash_site` column match `fuzzer.py:23,92` and `harness/dedup.py:56-58`.
- **N3 fixed.** ADR :118-121.
- **N4 fixed.** ADR :73.
- **N5 fixed.** ADR :76-79 matches `fuzzer.py:113` (any earlier crash's `path_id`/site is in
  the sets, because the sets only grow on save and an unsaved crash's pair is already present).
- **N6 fixed.** ADR :89-95. It matches `executor.py:17` (no `handle_*`).
- No `src/` or `harness/` change by this ticket (no AFL-030 trace; mtimes predate it).

Non-blocking:
- ADR :79 is one long line, a wrap nit.
- ADR :120 "the run ends early" means the exec. Tester may want "that exec ends early" for clarity.

## Test (tester, 2026-11-15): PASS

Verdict: PASS for the implementation (static test + ADR-0003 section). The ticket stays in
`tickets/testing/`. Closure waits on the lead's approval of the "Pre-registered contingency"
AC correction (false sentence "The monitor exists: AFL-012 already counts and flags `no_stack`
crashes"; draft in the orchestrator's stop2 notes). The open ACs (Contingency, both Ordering)
close only at the pilot and freeze, by design.

Gates (repo, no rebuild: the module fixtures' `make` reported "up to date"):
`ruff check .` all checks passed; `mypy src` no issues in 8 files;
`pytest --no-cov tests/test_target_static_check.py tests/test_dedup.py tests/test_fuzzer.py
tests/test_tlv_parser.py tests/test_mini_format.py -rA`: **82 passed, 3 deselected in 65.79s**
(19 static-check cases).

Per AC (option A):
- **Premise:** met. The static test is the gate, and it passes on all five `targets/*.c` files
  (cov_rt, mini_format, spike, tlv_parser, toy_parser).
- **Empirical record:** met. ADR-0003 has the 12-row table with Homebrew clang 23.1.3 and
  macOS 26.5 (25F71) arm64. Re-confirmed here: `clang --version` gives 23.1.3, `sw_vers`
  gives 26.5. `ASAN_OPTIONS=help=1` on a campaign-flag binary gives handle_segv=1,
  sigbus=1, sigfpe=1, abort=0, sigill=0, sigtrap=0.
- **Strict static check:** met. It globs at run time: a scratch `zz_new.c` containing
  `raise(6)` in a copied tree was collected and failed. Comments are stripped. The failure
  names the file and the form (`AssertionError: mini_format.c` / `['\\b__asm__\\b'] == []`).
  `static_assert` and comment-only text pass. `__builtin_abort` does not trip `\babort`.
- **ADR-0003 discloses (1)-(8):** met, every point present (ADR section "Stackless crashes
  merge under `no_stack`"). The text above that section matches the AFL-013 snapshot apart
  from one separator blank line.
- **Tripwire:** met (ADR-0003 "Tripwire" bullet).
- **Contingency:** open by design, since it needs the pilot. Checked against the drafted
  mechanism: a synthetic `pilot/<target>/<arm>/s<seed>/crash_events.csv` tree, written with
  the real `CRASH_COLUMNS`, gives per target and arm no_stack counts
  {mini_format/fast 0, mini_format/uniform 2, tlv_parser/fast 1, tlv_parser/uniform 0} as
  expected, using a stdlib `csv` count (layout from `run_campaign.py:423`).
- **No code change:** met. No AFL-030 trace in `src/` or `harness/`. The `src/` diffs belong
  to other tickets.
- **Ordering (A):** open by design (commit + `done/` before the freeze).
- **Both options:** "Decision recorded" met (Log 2026-11-14). For "Analysis recorded", the
  verdict is in Technical notes, not in the Log as the AC words it, so it needs a crew-lead
  tick or a Log line (reviewer noted this too). Non-blocking.
- **Cleanup check:** compared with the pre-cleanup snapshots, `tests/test_tlv_parser.py` lost
  only `BANNED`, the banned-form loop and the test rename. `tests/test_mini_format.py` lost
  the same three. Its other differences against older snapshots are AFL-016's bounce-1 work
  (BENIGN/STAIRCASE), logged in AFL-016. The no-`/`-or-`%` checks are kept in both files.

Mutation (copies under the tester's tmp only):
- All 18 BANNED forms were injected into copies of toy_parser.c, tlv_parser.c, mini_format.c
  and cov_rt.c: 72 injections. Each is flagged as exactly its own pattern, 0 mismatches.
  End to end via pytest on a copied tree, `__asm__("brk #1")` in mini_format.c fails
  `test_target_has_no_banned_form[mini_format.c]`.
- B1 reverted (delete-only `re.sub(r"/\*.*?\*/|//[^\n]*", "", ...)`): all 3
  `test_comment_stripping_bypasses_are_flagged` cases fail. `static_assert`/comments still
  pass.
- No stripping at all: `test_static_assert_and_comments_do_not_fail` fails, so that test is
  not vacuous.

ADR claims vs code:
- Saving rule: `fuzzer.py` `_Recorder.crash` saves iff `pid not in _crash_paths or site not
  in _crash_sites`. Checked live (below).
- Sentinel: `crash_site()` returns `"no_stack"` when no `#n 0x..` frame is found.
- `executor.py:17` `ASAN_OPTIONS = "abort_on_error=1:detect_leaks=0:symbolize=1"`, the same
  string as ADR-0002 :50. No `handle_*` in either.

Signal spot-check: a scratch `sigprobe.c` built with the Makefile's clang and flags
(`-g -O0 -fno-omit-frame-pointer -fsanitize=address -fsanitize-coverage=trace-pc-guard`,
plus cov_rt.c) and run through the real `Executor`, 2 runs per mode:
SIGILL `raise` gives SIGILL, no ASan report, `no_stack`. `__builtin_trap` gives SIGTRAP,
no report, `no_stack`. `abort()` gives SIGABRT, no report, `no_stack`. The null-write
control gives SIGABRT with an ASan report, `null_write`. Fed to `_Recorder`, the first event
per path_id was saved and repeats were not. A synthetic SIGBUS with SIGILL's edges wrote a
row (signal 10) and saved no file. `dedup.bucket_trial` gives one `no_stack` bucket
(count 7, `bug_id=None`) and `null_write` mapped to its bug. This matches ADR points 1-3.

Non-blocking notes:
- ADR-0003 point 3 has one long unwrapped line (reviewer nit, still present).
- The known items are unchanged: the contingency AC sentence (lead), the list gaps
  (`__asm`, `ualarm`, `syscall`; lead), and the three exotic bypasses.

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
- 2026-11-15 — implemented option A (developer): `tests/test_target_static_check.py`
  (globs `targets/*.c`, comments stripped, 18 banned forms; passes on toy_parser.c,
  tlv_parser.c, mini_format.c, cov_rt.c, spike.c; abort/assert/trap injection
  fails on each of the 3 campaign targets; `static_assert` and comment-only words
  do not fail) and ADR-0003 section "Stackless crashes merge under `no_stack`"
  (8 points, per-signal table with clang 23.1.3 / macOS 26.5 (25F71) arm64,
  tripwire, contingency), additions only. No `src/` change by this ticket. The banned
  list is copied from test_tlv_parser.py (not edited, under test). Left open for
  later: Pre-registered contingency (needs the pilot) and Ordering (needs the
  commit and `done/` before the freeze). Analysis and decision ACs are covered by
  the existing Log and Technical notes entries.
- 2026-11-15 — review: BOUNCE to in-progress (reviewer). B1 comment-strip false negatives (`tests/test_target_static_check.py:25`); B2 ADR-0003 contingency says AFL-012 "already counts" `no_stack` (not implemented; AC sentence escalated to req-engineer/human). Non-blocking N1-N6 in the Review section.
- 2026-11-15 — bounce 1 fixed (developer): B1 comment stripping is now one tokenising
  pass that keeps string/char literals (3 new flagged-bypass cases); B2 ADR-0003 no
  longer claims AFL-012 monitors `no_stack` (pilot count from `crash_events.csv`
  directly); N3-N6 ADR points 1, 3, 5, 8 reworded. Banned list and the two local
  test copies untouched.
- 2026-11-15 — re-review after bounce 1: APPROVE, moved to testing (reviewer). B1, B2 and N3-N6 verified. The gates passed (70 passed). No realistic stripping bypass was found, and the residual ones are non-blocking (in the Re-review section).
- 2026-11-15 — post-re-review cleanup: removed the local banned-form copy from tests/test_tlv_parser.py (list kept in AFL-030 only, per AFL-010/AFL-016 ACs); docstring updated; ADR-0003 point 8 wording clarified (developer)
- 2026-11-15 — test: PASS (tester). Gates green (82 passed, 3 deselected); 72/72 banned-form injections flagged, B1-revert mutant fails all 3 bypass cases; signal spot-check via real Executor confirms SIGILL/SIGTRAP/abort give `no_stack` and merge (ADR points 1-3). Stays in testing: closure waits on the lead's approval of the contingency-AC correction.
- 2026-11-15 — AC "Strict static source check": banned list gains `__asm`, `ualarm(` and `syscall(` (reviewer N2; lead decision, 2026-11-15), as a new sub-bullet in the list's existing form. ADR-0003 "Stackless crashes" point 4 is being updated by the architect to match. The static test (`tests/test_target_static_check.py`) does not yet hold the three forms, so this AC needs the developer's change and a re-test before closure. The pending "B2" correction to the "Pre-registered contingency" AC is not applied here; it awaits a lead decision (req-engineer)
- 2026-11-15 (developer): static check extended with __asm, ualarm( and syscall( per lead decision/ADR-0003 pt 4; tests/test_target_static_check.py: positive tests per new form, near-miss tests (identifiers, comments), string-literal behaviour pinned (flagged, same as old forms); real targets pass; ruff/mypy clean, 25 tests pass.
- 2026-11-15 — re-test after banned-list extension: PASS (tester). `BANNED` (21 patterns) equals ADR-0003 point 4 exactly: no form missing, no extras, no duplicates. Realistic spellings are flagged by their own pattern only: `__asm volatile("brk #1")`, `__asm ("nop")`, `__asm\nvolatile`, `__asm__ __volatile__`, `asm(`, `syscall(SYS_kill, ...)`, `syscall (SYS_exit, 1)`, `syscall\n(1)`, `ualarm (1,0)`. Mutation on scratch copies: removing `__asm`, `ualarm(` or `syscall(` from BANNED fails 2 tests each (its `test_new_banned_forms_are_flagged` case and the string-literal test). End to end on a scratch tree, one form injected into each campaign-target copy fails `test_target_has_no_banned_form` for that file, naming the form. Gates: `ruff check .` clean, `mypy src` clean (8 files), `pytest --no-cov tests/test_target_static_check.py` 25 passed; the real `targets/*.c` pass and were not modified. The "Strict static source check" tick is now honest. Stays in testing: closure waits on the lead's decision on B2 (the contingency AC sentence).
- 2026-11-15 — corrected the "Pre-registered contingency" AC (review B2): removed the false sentence "The monitor exists: AFL-012 already counts and flags `no_stack` crashes." (AFL-012 was in backlog with `harness/aggregate.py` a TODO stub, its sentinel flag covers main-campaign trials only, and AFL-011 excludes pilot results from AFL-012); the pilot count is now taken directly from each pilot trial's `crash_events.csv`, rows with `crash_site == "no_stack"`, summed per target and arm, written by the runner or the pilot evaluation step. Threshold (any such row, any target, either arm) and decision rule (the human reconsiders B before the AFL-011 freeze, outcome logged here) unchanged. (lead decision, 2026-11-15)
- 2026-11-15 — "Both options" boxes ticked (Analysis, Decision, Ordering). The analysis verdict (no, for toy_parser and tlv_parser; high confidence on code paths, medium overall; corrections from the condition-1 evidence) sits in the Technical notes section "First-pass analysis: can a planted target raise a stackless crash?" and "Condition-1 evidence", not in this Log; pointer recorded here. (lead decision, 2026-11-15)
- 2026-11-15 — "Pre-registered contingency" left UNTICKED, open by design: evaluated at the first pilot; tracked by AFL-011 pre-freeze checklist item (l). Option A "Ordering" ticked at close: the ticket is in `tickets/done/` before any freeze commit; the commit itself is the human's and must precede the freeze (AFL-011 checklist item (a)). (lead decision, 2026-11-15)
- 2026-11-15 — closed by crew-lead to done/ (lead decision, 2026-11-15). Every AC ticked with tester evidence except the contingency (above). Gates green at test (ruff, mypy, pytest) and re-test (25 static-check tests); no `src/` change by this ticket.
- 2026-11-15 — B2 text: stale "is not built and" dropped (AFL-012 is done); the runner or the pilot evaluation step writes the per-pilot no_stack counts, no human step (lead decision, 2026-11-15) (orchestrator)
