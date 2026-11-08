---
id: AFL-018
title: Classify every terminating signal as a crash (AFL rule), except our own timeout kill
requirement: FR-2 / NFR-1 (honesty of reported results); PRD §8 threats to validity
paper_ref: Klees § performance measures (honest crash counting and de-duplication); AFL whitepaper (any fatal signal is a crash); ADR-0002 Consequences
module: docs/PRD.md (FR-2), docs/adr/0002-asan-configuration.md, src/fuzzer/executor.py, tests/test_executor.py, tests/test_corpus.py
depends_on: [AFL-003]
status: backlog
owner: developer (PRD and ADR text staged for the human to read as a diff)
---

## Goal
`ExecResult.outcome` currently classifies a run killed by any signal other than
SIGSEGV or SIGABRT (e.g. SIGBUS, SIGILL, SIGFPE) as `"clean"`. Such a run then
reaches `Corpus.observe()`, can be retained as a seed, and is counted in f(i). It is
not counted as a crash. ADR-0002 accepted this and said widening the rule needs a
PRD ticket. This is that ticket. **Decided (human, 2026-11-07):** adopt AFL's rule.
Any run terminated by a signal is a `"crash"`, except a run killed by our own
timeout, which stays `"hang"`. This reverses ADR-0002's acceptance of SIGBUS, SIGILL
and SIGFPE as clean.

## Decision (resolved, human, 2026-11-07)
The open question (options a/b/c) is resolved in favour of a widened crash set
(former option (b)), with the signal list answered as "all terminating signals
except our own timeout kill":

- A run whose terminating signal is set is `"crash"`, whatever the signal.
- A run killed by the executor's own timeout is `"hang"` (precedence hang > crash >
  clean is unchanged).
- A non-zero exit status with no signal is `"clean"` (unchanged).

Rejected: (a) keep {SIGSEGV, SIGABRT} and disclose/guard; (c) add a distinct
non-clean `"signal"` outcome.

## Acceptance criteria
- [ ] **ADR-0002 amended in the same change.** ADR-0002 Consequences records the
      decision and its date (2026-11-07), states that every terminating signal
      except our own timeout kill is a crash, and replaces both the acceptance of
      SIGBUS/SIGILL/SIGFPE as clean and the sentence "Widening the rule needs a PRD
      ticket". The ADR edit is left unstaged/uncommitted for the human to read as a
      diff before commit.
- [ ] **PRD FR-2 updated.** PRD FR-2 states the same rule (crash = any terminating
      signal except the timeout kill; timeout kill = hang; non-signal non-zero exit =
      clean). The PRD diff is read verbatim by the human before commit.
- [ ] **PRD §8 threats to validity** (or FR-2 itself) states in one sentence how runs
      ended by a signal outside {SIGSEGV, SIGABRT} are treated: as crashes.
- [ ] **Code matches the text.** `src/fuzzer/executor.py`'s crash classification
      equals the PRD FR-2 rule exactly: `outcome == "crash"` iff the run was not
      killed by our timeout and its terminating signal is not `None`. If a named
      `CRASH_SIGNALS` set is kept, it is not consulted for the crash decision (or is
      removed).
- [ ] **Executor tests.** An `ExecResult` (or a real child) terminated by each of
      SIGBUS, SIGILL and SIGFPE has `outcome == "crash"`; SIGSEGV and SIGABRT are
      still `"crash"`; a timeout is still `"hang"` (precedence unchanged); a
      non-signal non-zero exit is still `"clean"`.
- [ ] **Corpus tests.** In `tests/test_corpus.py`, `Corpus.observe()` given a
      SIGBUS, a SIGILL and a SIGFPE result each raises `ValueError` and leaves seeds,
      seen-set, path counts and `path_freq` unchanged (extend the existing
      parametrized non-clean test).
- [ ] **No harness-caused SIGPIPE (human decision, 2026-11-07).** Under this rule
      any terminating signal is a crash, so a SIGPIPE caused by the harness (target
      writes to a stdout pipe the executor never drains or has closed, e.g. a
      `printf` in tlv_parser) would be counted as a bug. The executor connects the
      target's stdout to `subprocess.DEVNULL`, or to a pipe it fully drains. Test: a
      real child that writes a large amount to stdout (well beyond a pipe buffer,
      e.g. ≥1 MiB) and then exits 0 has `outcome == "clean"`, not `"crash"`.
      Current code (checked 2026-11-07): `Executor.run()` already passes
      `stdout=subprocess.DEVNULL` to `subprocess.run`, so this AC pins existing
      behaviour with a test and forbids regressing it.
- [ ] **AFL-013 (dedup) check.** AFL-013 is checked to bucket the added signals; any
      gap becomes a follow-up ticket.
- [ ] **Ordering.** This ticket lands before AFL-011's pre-registration freeze
      (AC "Pre-registered target retuning rule and freeze"), because it changes what
      the campaign counts as a crash.

## Technical notes (architect)
- Current code: `CRASH_SIGNALS = frozenset({SIGSEGV, SIGABRT})`; outcome precedence
  hang > crash > clean (src/fuzzer/executor.py). `Corpus.observe()` gates on
  `outcome != "clean"`, so no corpus code change is needed, only tests.
- NFR-2 is unaffected: both arms share the executor, so they classify identically.

## Test approach (tester)
Unit tests with synthetic `ExecResult` values (and, if cheap, a real child killed by
each signal). Verify PRD FR-2, ADR-0002 and executor.py agree exactly. Confirm the
corpus tests reject SIGBUS/SIGILL/SIGFPE and change no state. Confirm NFR-2 still
holds (both arms classify identically).

## Log
- 2026-11-07 — created (req-engineer) from AFL-004 review/test finding
- 2026-11-07 — batch grooming: open question resolved to AFL's rule (any terminating signal is a crash, except our own timeout kill, which stays "hang"), reversing ADR-0002's acceptance of SIGBUS/SIGILL/SIGFPE as clean; ACs rewritten for the chosen option (ADR-0002 amended in the same change, PRD FR-2 diff read by human, executor + corpus tests, lands before AFL-011 freeze); meets DoR (human decision) (req-engineer)
- 2026-11-07 — review fix: added SIGPIPE AC (target stdout to DEVNULL or a fully drained pipe; large-stdout child must be "clean"); noted executor.py already uses `stdout=subprocess.DEVNULL` (human decision) (req-engineer)
