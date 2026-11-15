---
id: AFL-022
title: Remove redundant bare-signal observe() from the corpus non-clean test
requirement: FR-3 / FR-2 (test hygiene for the corpus non-clean rejection test)
paper_ref: n/a
module: tests/test_corpus.py
depends_on: []
status: done
owner: developer
---

## Goal
In `tests/test_corpus.py`, `test_non_clean_raises_and_changes_nothing` (around lines
59–60) has a second `with pytest.raises(ValueError): c.observe(b"z",
ExecResult(None, 11, False, frozenset({1}), 0.0, b""))` using a bare signal `11`.
The parametrized `sigsegv` case already covers it, so it is redundant. Delete it.

## Acceptance criteria
- [x] The two lines (the `with pytest.raises(ValueError):` and the bare-signal-`11`
      `c.observe(...)` call beneath it) are removed from
      `test_non_clean_raises_and_changes_nothing`.
- [x] `pytest` passes.
- [x] No other change to `tests/test_corpus.py` (`git diff -- tests/test_corpus.py`
      shows only those two deleted lines).

## Technical notes (architect)
If AFL-018 lands first and extends the same parametrized test with SIGBUS/SIGILL/
SIGFPE cases, the line numbers shift; the target is still the bare-`11` block.

## Test approach (tester)
Run `pytest tests/test_corpus.py`; inspect `git diff -- tests/test_corpus.py`.

## Log
- 2026-11-07 — batch grooming: created (human decision) (req-engineer)
- 2026-11-15 — developer: deleted the redundant bare-signal-11 block (2 lines); ruff/mypy/test_corpus pass; diff is only those 2 deletions. Moved to review.
- 2026-11-15 — reviewer: APPROVE. AC1: diff removes exactly the `with pytest.raises(ValueError):` + bare-signal-11 `c.observe(...)` pair from test_non_clean_raises_and_changes_nothing (was tests/test_corpus.py:62-63 at HEAD). Coverage kept: parametrized `sigsegv` case (CRASH = signal.SIGSEGV, int 11 on this platform, tests/test_corpus.py:17,52) drives the same path, since ExecResult.outcome maps any non-None signal to "crash" (src/fuzzer/executor.py:34) and Corpus.observe raises on any non-clean outcome (src/fuzzer/corpus.py:40-41); the post-condition asserts (lines 62-63) still run for every case. AC2: pytest tests/test_corpus.py 15 passed, non_clean 6/6 (sigsegv/sigabrt/sigbus/sigill/sigfpe/hang); ruff clean on the file; full suite not run by reviewer (scope). AC3: git diff --stat = 1 file, 2 deletions, no other hunks; src/fuzzer/corpus.py and executor.py unmodified. Invariants: test-only change, no schedule/mutator/arm effect (NFR-2 and blind mutation untouched). Moved to testing.
- 2026-11-15 — tester: PASS. AC1: `git diff -- tests/test_corpus.py` removes exactly the `with pytest.raises(ValueError):` + bare-signal-11 `c.observe(...)` pair from test_non_clean_raises_and_changes_nothing. AC2: `pytest tests/test_corpus.py` 15 passed; ruff clean on the file (full suite not run, out of scope). AC3: `git diff --numstat` = 0 added / 2 deleted, single hunk. Coverage claim proven by mutation in a scratch copy (src/ + tests/test_corpus.py, outside the repo): M1 `Corpus.observe` accepts a signal-11 crash (`... and result.signal != 11`) -> test_non_clean_raises_and_changes_nothing[sigsegv] FAILS; M2 `ExecResult.outcome` treats signal 11 as clean -> same [sigsegv] case FAILS; both restored, scratch src identical to repo, 15 passed. signal.SIGSEGV == 11 on this platform, so the parametrized case is the same input the deleted line used. Left in testing for crew-lead close.
- 2026-11-15 — DoD verified, moved to done (crew-lead). All 3 ACs ticked on reviewer APPROVE and tester PASS evidence: `git diff --numstat -- tests/test_corpus.py` = 0 added / 2 deleted, single hunk removing exactly the bare-signal-11 pair; coverage kept by the parametrized [sigsegv] case (tester mutants M1/M2 killed). AC2 full `pytest` confirmed by the done-gate hook (ruff ., mypy src, pytest) at the move. Test-only change; NFR-2 and blind mutation untouched. Commit must reference AFL-022 (human's step).
