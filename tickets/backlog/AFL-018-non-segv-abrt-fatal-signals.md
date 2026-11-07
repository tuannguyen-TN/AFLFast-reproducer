---
id: AFL-018
title: Decide and disclose non-SEGV/ABRT fatal signals (SIGBUS, SIGILL, SIGFPE) classified as clean
requirement: FR-2 / NFR-1 (honesty of reported results); PRD §8 threats to validity
paper_ref: Klees § performance measures (honest crash counting and de-duplication); ADR-0002 Consequences
module: docs/PRD.md, docs/adr/0002-asan-configuration.md, src/fuzzer/executor.py (possibly), harness/ (possibly), report
depends_on: [AFL-003]
status: backlog
owner: req-engineer (then developer if FR-2 is widened or a new outcome is added)
---

## Goal
`ExecResult.outcome` classifies a run killed by any signal other than SIGSEGV or
SIGABRT (e.g. SIGBUS, SIGILL, SIGFPE) as `"clean"`. Such a run then reaches
`Corpus.observe()`, can be retained as a seed, and is counted in f(i). It is not
counted as a crash. ADR-0002 accepts this because the current targets do not raise
those signals, and says widening the rule needs a PRD ticket. This is that ticket:
decide the rule and make sure the report can never silently hide such runs.

**Not ready (DoR fails) until the human decides the open question below.** The
acceptance criteria are written per option and become binding only for the chosen
one.

## Open question (human decision)
Options, listed without a recommendation:

- **(a) Keep FR-2 as is, disclose and guard.** FR-2's crash set stays
  {SIGSEGV, SIGABRT}. The report's threats-to-validity section states that other
  fatal signals are classified as clean. The campaign counts every run whose
  terminating signal is set and not in the crash set, and fails or flags the trial
  if that count is ever nonzero.
- **(b) Widen FR-2's crash set.** PRD FR-2 is edited to name the extra signals
  (e.g. SIGBUS, SIGILL, SIGFPE) as crashes; ADR-0002 Consequences is updated;
  `CRASH_SIGNALS` in executor.py changes to match.
- **(c) Add a distinct non-clean outcome** (e.g. `"signal"`), neither retained in
  the corpus nor counted as a crash (and not in f(i)), recorded separately. Needs a
  PRD FR-2 edit, an ADR-0002 update, and handling in the main loop (AFL-007).

Sub-questions for (a): fail the trial, or flag it and keep it? For (b)/(c): exact
signal list (all non-zero signals except our own timeout kill, or a named set)?

## Acceptance criteria (conditional on the decision)
Common to every option:
- [ ] The decision and its date are recorded in this ticket and in ADR-0002
      Consequences (replacing "Widening the rule needs a PRD ticket").
- [ ] PRD §8 threats to validity (or the report's threats section) states, in one
      sentence, how runs ended by a signal outside {SIGSEGV, SIGABRT} are treated.

If **(a)**:
- [ ] PRD FR-2 text is unchanged; `CRASH_SIGNALS` is unchanged.
- [ ] Each trial's metrics record an integer `other_signal_runs` = number of
      executions with `signal is not None and signal not in CRASH_SIGNALS`. Test: a
      synthetic stream with one SIGBUS run yields `other_signal_runs == 1`; a stream
      with only clean/SIGSEGV/SIGABRT/hang runs yields 0.
- [ ] If `other_signal_runs > 0`, the campaign does what the human chose (trial
      marked failed, or flagged in the aggregate output). Test: the SIGBUS stream
      triggers that behaviour; the zero stream does not.

If **(b)**:
- [ ] PRD FR-2 lists the full crash signal set; `CRASH_SIGNALS` equals it exactly.
- [ ] Executor test: an `ExecResult` with each added signal has
      `outcome == "crash"`; a timeout is still `"hang"` (precedence unchanged); a
      non-signal non-zero exit is still `"clean"`.
- [ ] AFL-013 (dedup) is checked to bucket the added signals; any gap becomes a
      follow-up ticket.

If **(c)**:
- [ ] PRD FR-2 defines the new outcome and its signal set; `Outcome` gains the new
      literal; precedence is hang > crash > new outcome > clean.
- [ ] Executor test: each listed signal maps to the new outcome.
- [ ] Corpus test: `observe()` raises `ValueError` on the new outcome and leaves
      seeds, seen-set, path counts and `path_freq` unchanged.
- [ ] The run's metrics record a count of the new outcome; it is not included in
      crash counts or TTFC.

## Technical notes (architect)
- Current code: `CRASH_SIGNALS = frozenset({SIGSEGV, SIGABRT})`; outcome precedence
  hang > crash > clean (src/fuzzer/executor.py). `Corpus.observe()` gates on
  `outcome != "clean"`, so options (b) and (c) need no corpus change beyond a test.
- Options (b) and (c) change what the campaign counts as a crash, so whichever is
  chosen must land before AFL-011's pre-registration freeze, not after it.
- Option (a) touches harness only (AFL-007 counter, AFL-011/012 reporting); split
  into developer tickets once decided if scope exceeds one unit of work.

## Test approach (tester)
Unit tests with synthetic `ExecResult` values per the chosen option's ACs. For (a),
verify the counter and the fail/flag behaviour on a synthetic stream, and confirm
the report text exists. For (b)/(c), verify PRD, ADR-0002 and `CRASH_SIGNALS` /
`Outcome` agree exactly, and that NFR-2 still holds (both arms classify
identically).

## Log
- 2026-11-07 — created (req-engineer) from AFL-004 review/test finding
