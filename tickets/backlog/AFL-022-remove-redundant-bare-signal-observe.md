---
id: AFL-022
title: Remove redundant bare-signal observe() from the corpus non-clean test
requirement: FR-3 / FR-2 (test hygiene for the corpus non-clean rejection test)
paper_ref: n/a
module: tests/test_corpus.py
depends_on: []
status: backlog
owner: developer
---

## Goal
In `tests/test_corpus.py`, `test_non_clean_raises_and_changes_nothing` (around lines
59–60) has a second `with pytest.raises(ValueError): c.observe(b"z",
ExecResult(None, 11, False, frozenset({1}), 0.0, b""))` using a bare signal `11`.
The parametrized `sigsegv` case already covers it, so it is redundant. Delete it.

## Acceptance criteria
- [ ] The two lines (the `with pytest.raises(ValueError):` and the bare-signal-`11`
      `c.observe(...)` call beneath it) are removed from
      `test_non_clean_raises_and_changes_nothing`.
- [ ] `pytest` passes.
- [ ] No other change to `tests/test_corpus.py` (`git diff -- tests/test_corpus.py`
      shows only those two deleted lines).

## Technical notes (architect)
If AFL-018 lands first and extends the same parametrized test with SIGBUS/SIGILL/
SIGFPE cases, the line numbers shift; the target is still the bare-`11` block.

## Test approach (tester)
Run `pytest tests/test_corpus.py`; inspect `git diff -- tests/test_corpus.py`.

## Log
- 2026-11-07 — batch grooming: created (human decision) (req-engineer)
