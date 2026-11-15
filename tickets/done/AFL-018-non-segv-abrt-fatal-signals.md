---
id: AFL-018
title: Classify every terminating signal as a crash (AFL rule), except our own timeout kill
requirement: FR-2 / NFR-1 (honesty of reported results); PRD §8 threats to validity
paper_ref: Klees § performance measures (honest crash counting and de-duplication); AFL whitepaper (any fatal signal is a crash); ADR-0002 Consequences
module: docs/PRD.md (FR-2), docs/adr/0002-asan-configuration.md, src/fuzzer/executor.py, tests/test_executor.py, tests/test_corpus.py
depends_on: [AFL-003, AFL-028]
status: done
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
- [x] **ADR-0002 amended in the same change.** ADR-0002 Consequences records the
      decision and its date (2026-11-07), states that every terminating signal
      except our own timeout kill is a crash, and replaces both the acceptance of
      SIGBUS/SIGILL/SIGFPE as clean and the sentence "Widening the rule needs a PRD
      ticket". The ADR edit is left unstaged/uncommitted for the human to read as a
      diff before commit.
- [x] **PRD FR-2 updated.** PRD FR-2 states the same rule (crash = any terminating
      signal except the timeout kill; timeout kill = hang; non-signal non-zero exit =
      clean). The PRD diff is read verbatim by the human before commit.
      Evidence: PRD line 85 (FR-2 row) now carries the bounce-1 text; the old anchor is gone.
- [x] **PRD §8 threats to validity** (or FR-2 itself) states in one sentence how runs
      ended by a signal outside {SIGSEGV, SIGABRT} are treated: as crashes.
      Evidence: new "Crash classification" paragraph at the end of the §8 Threats-to-validity bullet.
- [x] **Code matches the text.** `src/fuzzer/executor.py`'s crash classification
      equals the PRD FR-2 rule exactly: `outcome == "crash"` iff the run was not
      killed by our timeout and its terminating signal is not `None`. If a named
      `CRASH_SIGNALS` set is kept, it is not consulted for the crash decision (or is
      removed).
- [x] **Executor tests.** An `ExecResult` (or a real child) terminated by each of
      SIGBUS, SIGILL and SIGFPE has `outcome == "crash"`; SIGSEGV and SIGABRT are
      still `"crash"`; a timeout is still `"hang"` (precedence unchanged); a
      non-signal non-zero exit is still `"clean"`.
- [x] **Corpus tests.** In `tests/test_corpus.py`, `Corpus.observe()` given a
      SIGBUS, a SIGILL and a SIGFPE result each raises `ValueError` and leaves seeds,
      seen-set, path counts and `path_freq` unchanged (extend the existing
      parametrized non-clean test).
- [x] **No harness-caused SIGPIPE (human decision, 2026-11-07).** Under this rule
      any terminating signal is a crash, so a SIGPIPE caused by the harness (target
      writes to a stdout pipe the executor never drains or has closed, e.g. a
      `printf` in tlv_parser) would be counted as a bug. The executor connects the
      target's stdout to `subprocess.DEVNULL`, or to a pipe it fully drains. Test: a
      real child that writes a large amount to stdout (well beyond a pipe buffer,
      e.g. ≥1 MiB) and then exits 0 has `outcome == "clean"`, not `"crash"`.
      Current code (checked 2026-11-07): `Executor.run()` already passes
      `stdout=subprocess.DEVNULL` to `subprocess.run`, so this AC pins existing
      behaviour with a test and forbids regressing it.
- [x] **AFL-013 (dedup) check.** AFL-013 is checked to bucket the added signals; any
      gap becomes a follow-up ticket. Follow-up: AFL-030.
- [x] **ADR-0005 `edges` definition (R1, deferred).** Edit docs/adr/0005-stopping-and-exec-index-replay.md lines ~311-312 after the AFL-011 pre-registration commit lands. Current: `"Clean" is the executor's outcome (AFL-003, ADR-0002): not timed out, and not killed by SIGSEGV or SIGABRT. A nonzero exit status is clean.` Replacement: `"Clean" is the executor's outcome (AFL-003, ADR-0002, AFL-018): not timed out, and not ended by any signal. A nonzero exit status with no signal is clean.`
      Evidence: applied in ADR-0005 §6 `edges` bullet, re-wrapped; no other ADR-0005 text changed by this ticket.
- [x] **Ordering.** This ticket lands before AFL-011's pre-registration freeze
      (AC "Pre-registered target retuning rule and freeze"), because it changes what
      the campaign counts as a crash.
      Evidence: code, tests, ADR-0002, PRD FR-2/§8 and ADR-0005 edits are all in the working tree for the human's commit-time diff read, ahead of the freeze.

## Technical notes (architect)
- Current code: `CRASH_SIGNALS = frozenset({SIGSEGV, SIGABRT})`; outcome precedence
  hang > crash > clean (src/fuzzer/executor.py). `Corpus.observe()` gates on
  `outcome != "clean"`, so no corpus code change is needed, only tests.
- NFR-2 is unaffected: both arms share the executor, so they classify identically.
- Start only after the AFL-028 diff is committed (both edit executor.py/tests/test_executor.py; keeps hunks separable).

## Test approach (tester)
Unit tests with synthetic `ExecResult` values (and, if cheap, a real child killed by
each signal). Verify PRD FR-2, ADR-0002 and executor.py agree exactly. Confirm the
corpus tests reject SIGBUS/SIGILL/SIGFPE and change no state. Confirm NFR-2 still
holds (both arms classify identically).

## Log
- 2026-11-07 — created (req-engineer) from AFL-004 review/test finding
- 2026-11-07 — batch grooming: open question resolved to AFL's rule (any terminating signal is a crash, except our own timeout kill, which stays "hang"), reversing ADR-0002's acceptance of SIGBUS/SIGILL/SIGFPE as clean; ACs rewritten for the chosen option (ADR-0002 amended in the same change, PRD FR-2 diff read by human, executor + corpus tests, lands before AFL-011 freeze); meets DoR (human decision) (req-engineer)
- 2026-11-07 — review fix: added SIGPIPE AC (target stdout to DEVNULL or a fully drained pipe; large-stdout child must be "clean"); noted executor.py already uses `stdout=subprocess.DEVNULL` (human decision) (req-engineer)
- 2026-11-12 — depends_on += AFL-028, matching the INDEX row; Technical notes: start only after the AFL-028 diff is committed, since both edit executor.py and tests/test_executor.py (human decision, 2026-11-12) (req-engineer)
- 2026-11-14 — implemented (developer). executor.py: `CRASH_SIGNALS` removed (only other users were done-ticket text); `outcome` is hang if timed_out, crash if signal is not None, else clean. tests/test_executor.py: SIGBUS/SIGILL/SIGFPE added to the real-child crash parametrization (`kill -BUS $$` etc.); `kill -TERM` test reversed to crash; new SIGPIPE test (child writes 2 MiB to stdout, exits 0 -> clean). tests/test_corpus.py: SIGBUS/SIGILL/SIGFPE added to the non-clean parametrized test. ADR-0002 Consequences amended (2026-11-07 decision); other ADR text untouched, including Context line 9 ("FR-2 counts a crash only if SIGSEGV or SIGABRT"), which describes the pre-amendment rule and is left for the human to decide. ruff, mypy, pytest pass; new signal tests 20/20 runs green.
- 2026-11-14 — PRD FR-2 and §8 edits deferred until the AFL-011 pre-registration commit lands, to keep PRD hunks separable (orchestrator sequencing). The two PRD ACs stay unchecked, as does Ordering (human commit decision).
- 2026-11-14 — AFL-013 check (read-only; harness/dedup.py is a 7-line stub). The design buckets every `crash_events.csv` row by `crash_site` regardless of signal, so SIGBUS/SIGILL/SIGFPE crashes ARE bucketed, never dropped: with an ASan report they key on the first in-target frame (ASan with abort_on_error=1 usually turns BUS/FPE into SIGABRT with a report); with no report (e.g. a bare SIGILL, or SIGFPE with ASan not handling it) `crash_site()` returns "no_stack", which gets its own unknown bucket (bug_id=None). Gap: the key excludes the signal (human decision), so all stackless crashes of different signals merge into one "no_stack" bucket, and none can map to a planted bug. Follow-up proposal: "AFL-0NN: signal-aware sentinel for stackless crashes. AFL-013 buckets any crash with an empty or stackless ASan report under the single sentinel `no_stack`, so a SIGILL, SIGBUS and SIGFPE crash with no report merge into one unknown bucket and are never attributable to a planted bug. Decide whether the stackless sentinel should carry the signal (e.g. `no_stack:SIGILL`) in the crash_site written by AFL-007's extractor/recorder, which keeps dedup site-only while keeping distinct stackless signals apart; confirm that no planted target (toy_parser, tlv_parser, mini-format) raises such a crash today, and if none does, record the merge as a disclosed bias in ADR-0003 instead of changing the key. Depends on AFL-007 and AFL-013; must land before the AFL-011 freeze if it changes crash_site."
- 2026-11-14 — PROPOSED PRD TEXT (SUPERSEDED by the bounce-1 text below; kept for history), to apply verbatim later.
  - FR-2 table row, replace "SIGSEGV/SIGABRT classified as crash" with: "any terminating signal is classified as crash, except a run killed by the executor's own timeout, which is a hang; a non-zero exit with no signal is clean (precedence hang > crash > clean)".
  - §8 threats-to-validity sentence: "Runs ended by a signal other than SIGSEGV or SIGABRT (e.g. SIGBUS, SIGILL, SIGFPE) are counted as crashes, following AFL's rule; only our own timeout kill is excluded (ADR-0002, AFL-018)."
- 2026-11-14 — PROPOSED PRD TEXT (bounce 1, current; addresses N3, N4), apply verbatim later.
  - FR-2: "a run ended by any terminating signal is a crash, except a run killed by the executor's own timeout, which is a hang; a non-zero exit with no signal is clean (precedence hang > crash > clean)"
  - §8: "Runs ended by a signal other than SIGSEGV or SIGABRT (e.g. SIGBUS, SIGILL, SIGFPE) are counted as crashes, following AFL's rule; only our own timeout kill is excluded (ADR-0002, AFL-018). This includes signals not raised by the target (e.g. an OS kill under memory pressure), which appear as stackless crashes."
- 2026-11-14 — ADR-0005 `edges` definition (lines ~311-312) deferred with the PRD text until the AFL-011 pre-registration commit lands (orchestrator sequencing). Exact replacement recorded in the new unchecked AC.
- 2026-11-14 — AFL-013 gap follow-up being filed as AFL-030 (req-engineer); AC re-ticked when the file exists.
- 2026-11-14 — bounce 1 (developer). Fixed: N2 (synthetic ExecResult timed_out=True + SIGKILL -> "hang", tests/test_executor.py), N5 (ADR-0002 "stricter than" -> "a superset of (broader than)"), N3/N4 (PRD text updated, old text marked superseded), R2 (AFL-013 AC unticked). Deferred: R1 (ADR-0005, new unchecked AC), PRD FR-2/§8 edits, AFL-030 filing, Ordering. Status stays in-progress.
- 2026-11-14 — ADR-0002 Context line 9 kept as history, with a pointer added: "(as originally written; amended 2026-11-07 by AFL-018, see Consequences)" (orchestrator request) (developer)
- 2026-11-14 — review: CHANGES REQUESTED → in-progress (bounce 1). Code, tests and ADR-0002 are correct; two doc/process items block: (R1) ADR-0005 §edges (line 311-312, committed text) still defines clean as "not killed by SIGSEGV or SIGABRT", now false; (R2) AFL-013-check AC ticked but the follow-up ticket exists only as a Log proposal. See Review section (reviewer)
- 2026-11-14 — AFL-013 gap filed as AFL-030 (2026-11-14); AC re-ticked.
- 2026-11-14 — re-review after bounce 1: APPROVED → testing. R1 deferral accepted as orchestrator sequencing (replacement text verified correct and complete); R2 closed by AFL-030; N2/N3/N4/N5 addressed. Open, by design: PRD FR-2, PRD §8, ADR-0005 edges AC, Ordering (reviewer)
- 2026-11-14 — tester: verified (non-deferred ACs); ready to close once deferred ACs are applied. Verified in the working tree (no clean checkout available). Non-blocking: rare load flake in the 1.0 s `run_script` timeout (1 of 55 loop runs); see Test section (tester)
- 2026-11-14 — developer: deferred ACs applied (PRD FR-2, PRD §8, ADR-0005 §6 edges) and run_script timeout 5.0 s for non-hang callers (tester follow-up; lead decision, 2026-11-14)
- 2026-11-14 — re-review (deferred ACs + run_script timeout): APPROVED → testing. PRD FR-2, PRD §8 and ADR-0005 `edges` text verified verbatim against the bounce-1 text and the AC; no stale statement of the old rule in docs/ or src/; 5.0 s default affects non-hang callers only (reviewer)
- 2026-11-14 — tester: deferred ACs verified (PRD FR-2 :85, PRD §8 :210, ADR-0005 :310-312), run_script 5.0 s default checked (hang callers explicit 0.3 s, no assertion weakened); 32/32 load loops green (37 tests each, 6x `yes`); mypy, ruff pass. PASS, ready to close (crew-lead). Ordering remains the human's commit-time item (tester)
- 2026-11-14 — closed (crew-lead): DoD verified; all 10 ACs ticked with evidence; review (3 passes, final APPROVED) and test (2 passes, final PASS) sections present; Log complete. Known exceptions: verified in the working tree, not a clean checkout (tester-documented); the commit with the AFL-018 id and the Ordering landing before the AFL-011 freeze are the human's commit-time items. testing → done (crew-lead)

## Review (reviewer, 2026-11-14) — CHANGES REQUESTED → in-progress (bounce 1)

Gates: `ruff check .` all checks passed; `mypy src` no issues (8 files); `pytest` 256 passed,
2 deselected. AFL-018 tests (executor + corpus selection) 15/15 loops green.

Per AC:
- ADR-0002 amended — PASS. Consequences bullet dated 2026-11-07, states the rule, replaces the
  SIGBUS/SIGILL/SIGFPE-clean text and "Widening the rule needs a PRD ticket". Context line 9 kept
  as history with a pointer to the amendment. Line 67 ("a crash under FR-2 as written") stays true
  (SIGABRT is a crash under both rules).
- PRD FR-2 / PRD §8 — deferred (known, orchestrator sequencing). Proposed text checked: correct
  and consistent with `ExecResult.outcome`. Wording notes below (N3, N4).
- Code matches the text — PASS. `outcome`: hang if `timed_out`, crash if `signal is not None`,
  else clean. `CRASH_SIGNALS` removed; no remaining reader in src/, harness/, tests/.
- Executor tests — PASS. Real children killed by SEGV/ABRT/BUS/ILL/FPE → crash; `kill -TERM` →
  crash; `exit 3` → clean; `sleep` → hang.
- Corpus tests — PASS. BUS/ILL/FPE added to the parametrized non-clean test (fixture asserts its
  own outcome, then checks raise + no state change).
- No harness-caused SIGPIPE — PASS. 2 MiB to stdout, exit 0 → clean. An undrained pipe would hang
  (→ "hang"), a closed one would SIGPIPE (→ "crash"); both fail the test.
- AFL-013 check — NOT MET (R2). The analysis is right, but "any gap becomes a follow-up ticket":
  no ticket file exists; the follow-up is only proposed in the Log.
- Ordering — orchestrator's commit-time item (known).

Mutation check (monkeypatched `ExecResult.outcome`, no file edits): old rule {SEGV, ABRT} fails 7
tests (3 executor signal cases, TERM test, 3 corpus cases); "any signal except TERM" fails the
TERM test; "non-zero exit is crash" fails `test_clean_nonzero_exit` and
`test_cov_rt_failure_is_clean_via_executor`. Survivor: swapping the hang/crash checks (no fixture
has `timed_out=True` with a signal set; the executor never builds one) — see N2.

Invariants: executor has no RNG and no schedule knowledge; both arms share it (NFR-2 intact);
mutator untouched (blind-mutation invariant intact).

Downstream readers: `corpus.observe` (`!= "clean"` gate, unchanged, correct); fuzzer.py
first-exec instrumentation check (now a stackless SIGTERM'd first seed raises ValueError from
observe rather than the "no instrumentation" RuntimeError — better); fuzzer.py crash branch:
simulated SIGTERM/SIGILL/SIGBUS stackless crashes through `crash_site` + `_Recorder.crash`:
site "no_stack", one `crash_events.csv` row per event with the numeric signal, input saved per
the AFL-007 (path_id, site) rule, JSON sidecar records `signal`. Flows correctly. harness/ is
stubs only.

Required changes:
- R1 (medium, spec contradiction). docs/adr/0005-stopping-and-exec-index-replay.md lines
  311-312 (committed text, `edges` definition): "Clean" is the executor's outcome (AFL-003,
  ADR-0002): not timed out, and not killed by SIGSEGV or SIGABRT." After this change that is
  false (a SIGBUS/SIGTERM run is not clean) and it defines a primary metric the AFL-011 freeze
  pins. Proposed replacement: "not timed out, and not ended by any signal (AFL-018)". Either edit
  it in this change (the hunk is ≥ 39 lines from the uncommitted AFL-007 hunks, so it stages
  separately), or defer it with the PRD text and leave a matching unchecked item here. The human
  reads the diff (pre-registration-adjacent).
- R2 (process). File the stackless-sentinel follow-up as a backlog ticket (req-engineer) and
  record its ID here, or untick the AFL-013 AC until it exists. Add to it: under the AFL-007
  storage rule, stackless crashes of different signals at the same `path_id` share the key
  (path_id, "no_stack"), so only the first input is saved (verified by simulation); event rows
  still carry each signal, so counts are unaffected.

Notes (non-blocking):
- N1 (low). Signals not raised by the target now count as crashes: an OS memory-pressure
  SIGKILL, or Ctrl-C's SIGINT reaching the child (same process group) before Python raises
  KeyboardInterrupt — one spurious crash row in a trial that is being aborted anyway. AFL has
  the same rule but skips `stop_soon`. Consider naming this in the §8 sentence.
- N2 (low). Add a synthetic `ExecResult(None, SIGKILL, True, ...)` → "hang" assertion to pin
  precedence independent of the executor's construction.
- N3 (wording, PRD FR-2). "any terminating signal is classified as crash" classifies a signal,
  not a run; suggest "a run ended by any terminating signal is a crash, except ...". Otherwise
  correct, including precedence and the non-signal non-zero exit.
- N4 (wording, PRD §8). Correct as written. Optional: append "including signals not raised by
  the target (e.g. an OS kill), which appear as stackless crashes" (N1).
- N5 (pre-existing). ADR-0002 line 99 "stricter than plain AFL's signal-only crashes": the set
  is a superset, so "broader" (or "catches more than") is clearer. Not introduced here.

## Review (reviewer, 2026-11-14, re-review after bounce 1) — APPROVED → testing

Gates: `ruff check .` all checks passed; `mypy src` no issues (8 files); `pytest` 257 passed,
2 deselected. tests/test_executor.py + tests/test_corpus.py: 37 passed, 10/10 loops.

Findings from bounce 1:
- R1 — deferral accepted (orchestrator sequencing). New unchecked AC checked: its "Current" text
  matches docs/adr/0005-stopping-and-exec-index-replay.md lines 310-312 verbatim; the replacement
  ("not timed out, and not ended by any signal. A nonzero exit status with no signal is clean.")
  matches `ExecResult.outcome` exactly and is the only old-rule sentence in ADR-0005 (grep), so it
  is complete. The tester must not close the ticket while this AC is unchecked.
- R2 — closed. tickets/backlog/AFL-030-stackless-crash-signal-merge.md exists, is in INDEX.md,
  carries the storage-rule second effect, and gates the AFL-011 freeze. AC re-ticked correctly.
- N2 — closed. `test_timed_out_with_signal_is_hang`; the hang/crash swap mutant that survived
  bounce 1 now fails it.
- N3/N4 — closed. Current PRD text in the Log is correct and consistent with the code; old text
  marked SUPERSEDED.
- N5 — closed. ADR-0002 now says "a superset of (broader than)".

Every non-deferred AC is met; invariants (no RNG, no schedule knowledge in the executor, NFR-2,
blind mutation) unchanged. Deferred and open by design: PRD FR-2, PRD §8, ADR-0005 `edges`
definition (all applied after the AFL-011 pre-registration commit), Ordering (commit time).

## Test (tester, 2026-11-14) — PASS (non-deferred ACs); stays in testing

Verified in the working tree, not on a clean checkout (checkout/worktree unavailable); the
AFL-018 hunks sit alongside uncommitted AFL-007/011/015 work, which was treated as baseline.

Gates: `ruff check .` all checks passed; `mypy src` no issues (8 files); `pytest` 257 passed,
2 deselected (cov 99%). Extra: `pytest -m slow` 2 passed (built targets up to date, `make -q` rc 0).

Real children through the real `Executor` (throwaway script, 26/26 as expected):
`kill -SEGV/ABRT/BUS/ILL/FPE/TERM/PIPE/KILL/INT/USR1 $$` and python `signal.raise_signal`
(SEGV/BUS/ILL/FPE/TERM) -> crash with signal set, exit None; `exit 3`, `exit 0` -> clean;
`exec sleep 5` at timeout 0.5 -> hang; 2 MiB to stdout then exit 0 (head and python) -> clean.
Planted bugs (built binaries): toy_parser `BUGa` -> crash, SIGABRT, ASan "SEGV on unknown
address" (toy-1); toy_parser `!aaa` -> crash, heap-buffer-overflow (toy-2); tlv_parser
`A\x64`+100 bytes -> crash, stack-buffer-overflow. Benign inputs -> clean with edges.

Flakiness (signal/outcome tests, 20 per run): loop 1, 25 runs under 4x `yes` (10 cores, load
~6.5): 24/25 green; run 13 failed `test_crash_signals[SIGFPE]` and
`test_any_other_signal_is_crash` with outcome "hang" (fresh `/bin/sh` child overran the
`run_script` default `timeout_s=1.0`). Loop 2, 30 runs under 6x `yes` (load ~8): 30/30.
Latency probe, 300 fresh scripts under 8x `yes`: median 0.118 s, max 0.28 s, none > 1 s.
Total 1100 test executions, 2 failures, both in one run.
- T1 (low, non-blocking, test-only): the margin is the pre-existing `run_script` 1.0 s
  default (AFL-003), now relied on by 7 tests instead of 3. Code is correct; the
  classification is right whenever the child finishes in time. Suggested follow-up: give the
  non-hang `run_script` callers a generous timeout (e.g. 5.0 s, as the large-stdout test
  already does). Does not gate this ticket.

Klees validity: fuzzer.py builds one `Executor(cfg.target, cfg.timeout_s)`; `cfg.schedule`
is read only for `assign_energy`, so both arms share one crash definition (NFR-2). executor.py
and coverage.py contain no RNG. Crash rule recorded in ADR-0002 Consequences now; PRD text
is deferred but must land before the AFL-011 freeze (Ordering AC).

Deferred texts (applicable verbatim):
- FR-2: the anchor "SIGSEGV/SIGABRT classified as crash" occurs once (PRD line 85); the
  AFL-011 PRD diff does not touch it. The bounce-1 Log entry omits the anchor (only the
  superseded entry names it): T2 (low) — apply as "replace that anchor with the bounce-1 text".
- §8: sentence is exact, but no insertion point is named. T3 (low): suggest appending it as
  its own paragraph to the Threats-to-validity bullet (PRD line 166), after the "Platform"
  paragraph.
- ADR-0005: the "Current" text matches lines 310-312 only whitespace-normalised (line-wrapped,
  2-space bullet indent); it is the only old-rule sentence. T4 (low): AC says ~311-312;
  re-wrap the replacement to the bullet's indentation when applying.

## Review (reviewer, 2026-11-14, deferred ACs) — APPROVED → testing

Scope: afl018-docs.patch (PRD FR-2, PRD §8, ADR-0005 §6) and the `run_script` default timeout
in tests/test_executor.py. Other uncommitted PRD/ADR hunks (AFL-011) not reviewed here.

Gates: `mypy src` no issues (8 files); `ruff check` on src/, tests/test_executor.py,
tests/test_corpus.py all passed (repo-wide `ruff check .` currently reports 2 errors, both in
other tickets' files: tests/test_dedup.py:7 F401, tests/test_tlv_parser.py:55 FURB167);
`pytest tests/test_executor.py tests/test_corpus.py` 37 passed (~5 s), 6/6 runs green.

Per deferred AC:
- PRD FR-2 — PASS. docs/PRD.md:85 replaces the "SIGSEGV/SIGABRT classified as crash" anchor
  (now gone; T2) with the bounce-1 text verbatim, plus an attribution suffix. Reads correctly
  in the cell after "returns (exit status, terminating signal, coverage);"; no `|` added, so the
  table row keeps 4 columns. Matches `ExecResult.outcome` (hang > crash > clean).
- PRD §8 — PASS. docs/PRD.md:210, own paragraph at the end of the Threats-to-validity bullet
  (starts line 166), after "Platform" and before "## 9" (T3). Both sentences verbatim, including
  the N1/N4 stackless-signal clause.
- ADR-0005 `edges` — PASS. docs/adr/0005-stopping-and-exec-index-replay.md:310-312 carry the
  AC replacement verbatim, re-wrapped to the 2-space bullet indent (T4). No other ADR-0005
  sentence states the rule (line 190 "The signal is not part of it." is about the crash_site
  key, still true).
- Ordering — unchanged: commit-time item, ahead of the AFL-011 freeze.

Stale-rule grep (docs/, src/, harness/, README.md, CLAUDE.md, targets/, tickets/backlog,
tickets/in-progress): only hits are docs/PRD.md:210 (the new sentence, names the old set on
purpose) and docs/adr/0002-asan-configuration.md:9 (history, with the "amended 2026-11-07 by
AFL-018" pointer, accepted in bounce 1). targets/*.c and ADR-0002:66-78 describe ASan turning
findings into SIGABRT, not the classification rule. `CRASH_SIGNALS`: no hits.

run_script 5.0 s default — PASS. Every hang caller (tests/test_executor.py:63, 131, 144, 215,
233) passes `timeout_s=0.3` explicitly, so none waits 5 s or changes its assertions
(test_hang still bounds wall time at 0.3 + 1 s). Callers on the default (33, 42, 47, 72) all
expect a non-hang outcome; a longer bound only removes the load flake (T1). The 1.0 s defaults
in tests/test_fuzzer.py:51 and tests/test_cli.py:26 are fake executors, unrelated.

No other file changed for this ticket. Note (cosmetic, non-blocking): the §8 paragraph
capitalises after its label ("Crash classification: Runs"), the neighbouring "Timing-dependent
hangs: whether" does not; the human may harmonise at diff-read time.

## Test (tester, 2026-11-14, deferred ACs) — PASS; ready to close

Verified in the working tree (no clean checkout). Scope: the deferred doc ACs and the
`run_script` default timeout. Non-deferred ACs passed in the earlier Test section.

Per deferred AC:
- PRD FR-2 — PASS. docs/PRD.md:85: the "SIGSEGV/SIGABRT classified as crash" anchor is
  replaced (T2) by the bounce-1 FR-2 text verbatim, plus "*(AFL-018, human decision
  2026-11-07)*". The row keeps 4 columns. Text matches `ExecResult.outcome`
  (src/fuzzer/executor.py:31-36: hang if timed_out, crash if signal is not None, else clean).
- PRD §8 — PASS. docs/PRD.md:210: own "Crash classification" paragraph at the end of the
  Threats-to-validity bullet, after "Platform" and before "## 9" (T3). Both bounce-1 sentences
  verbatim.
- ADR-0005 `edges` — PASS. docs/adr/0005-stopping-and-exec-index-replay.md:310-312 carry the AC
  replacement verbatim, re-wrapped to the 2-space bullet indent (T4); the git diff for this
  hunk changes only that sentence.
- Ordering — not a tester item: the edits sit in the working tree ahead of the AFL-011 freeze;
  landing order is the human's commit decision.
- Stale-rule grep (docs/, src/, harness/, README.md, CLAUDE.md): only docs/PRD.md:210 (names the
  old set on purpose) and docs/adr/0002-asan-configuration.md:9 (history, with the amendment
  pointer). `CRASH_SIGNALS`: no hits.

run_script default 5.0 s (tests/test_executor.py:24) — PASS. Hang callers all pass
`timeout_s=0.3` explicitly (:63, :131, :144, :215, :233); test_hang still bounds wall time at
0.3 + 1 s (:64). Default callers (:33, :42, :47, :72) all expect non-hang outcomes. The diff of
tests/test_executor.py against HEAD changes only the default, adds the AFL-018 tests, and reverses
the TERM test as the AC requires; no other assertion changed. Direct `Executor(...)` callers
(:84, :106, :121, :155) are untouched.

Load check (T1 follow-up): `pytest tests/test_executor.py tests/test_corpus.py`, 37 tests per
run, 32 runs under 6x `yes` on 10 cores (load avg 6.5 rising to 17.4 with other agents' work):
32/32 green, 1184 test executions, 0 failures. All load generators killed afterwards. T1 closed.

Gates: `mypy src` no issues (8 files); `ruff check src tests/test_executor.py
tests/test_corpus.py` all passed; repo-wide `ruff check .` also all passed at test time (the
tests/test_dedup.py and tests/test_tlv_parser.py errors the reviewer saw are gone).

Verdict: PASS. Every AC is met; ready for crew-lead to close.

## Close (crew-lead, 2026-11-14)
DoD met: every AC ticked with evidence (AFL-013 gap filed as AFL-030); reviewer APPROVED and tester PASS on both the non-deferred and deferred ACs; Log complete. Spot-checked: docs/PRD.md:85 (FR-2) and :210 (§8), docs/adr/0005-stopping-and-exec-index-replay.md:310-312, `ExecResult.outcome` in src/fuzzer/executor.py, no `CRASH_SIGNALS` left. Open for the human: commit with the AFL-018 id, landing ahead of the AFL-011 freeze (Ordering), done from the working tree rather than a clean checkout. Closed → done.
