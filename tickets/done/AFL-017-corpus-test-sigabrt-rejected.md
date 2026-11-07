---
id: AFL-017
title: Corpus test — SIGABRT crash outcome rejected by observe()
requirement: FR-3 / FR-2
paper_ref: Klees § performance measures (honest crash counting; a crash must never enter the corpus or f(i)); ADR-0002 (ASan abort_on_error=1 → SIGABRT)
module: tests/test_corpus.py
depends_on: [AFL-004]
status: done
owner: developer
---

## Goal
Close a test gap found in AFL-004 review/test. The clean-only rule of
`Corpus.observe()` is tested only with a SIGSEGV crash (signal 11) and a hang. A
mutant that rejects only `signal == SIGSEGV` (or only timeouts) survived the
tester's mutation check. SIGABRT is the signal ASan raises under
`abort_on_error=1` (ADR-0002), so it is the main crash path in our targets. Pin it
with a test. Test-only: `src/fuzzer/corpus.py` does not change.

## Acceptance criteria
- [ ] `tests/test_corpus.py` has a crash case built as an `ExecResult` with
      `signal=signal.SIGABRT` (value 6), `timed_out=False`, `exit_status=None`,
      non-empty edges, and it is in the `parametrize` list of
      `test_non_clean_raises_and_changes_nothing` next to the existing SIGSEGV and
      hang cases.
- [ ] The test asserts that the SIGABRT result has `outcome == "crash"`, so the
      case cannot pass vacuously if the fixture is wrong.
- [ ] For the SIGABRT case, `observe()` raises `ValueError`. After the raise,
      `seeds`, the seen-set, the total of the path counts, and every existing
      seed's `path_freq` are unchanged (same assertions as the SIGSEGV case).
- [ ] Mutation check: a throwaway copy of `corpus.py` whose guard is changed to
      reject only `result.signal == signal.SIGSEGV or result.timed_out` (i.e.
      SIGABRT treated as clean) makes the suite fail. The unmodified `corpus.py`
      passes.
- [ ] `git diff --stat` for the ticket touches only `tests/test_corpus.py`; no
      change to `src/fuzzer/corpus.py` or `src/fuzzer/executor.py`.
- [ ] `ruff check .`, `mypy src` and `pytest` are green.

## Technical notes (architect)
- Use `signal.SIGABRT` from the stdlib, not a bare `6`, so intent is explicit.
- Optional, in scope: the second `observe()` call inside the existing test
  (L55) repeats a SIGSEGV crash and adds nothing; it may be dropped once the
  parametrized SIGABRT case exists. Do not weaken any existing assertion.
- No production code change. The real guard (`outcome != "clean"`) is already
  correct; a direct probe in AFL-004's Test section confirmed it.

## Test approach (tester)
Run the gates on a clean checkout. Then, in a scratch copy of the repo only (never
the working tree), replace the `observe()` guard with the SIGSEGV-only mutant above
and run `pytest tests/test_corpus.py`: it must fail, and the failing test id must
be the SIGABRT parametrization. Also re-run the existing "only timeout" mutant and
confirm it is still killed. Discard the scratch copy.

## Log
- 2026-11-07 — created (req-engineer) from AFL-004 review/test finding
- 2026-11-07 — implemented (developer, sonnet); reviewed: APPROVE to testing — all 6 ACs pass, SIGSEGV-only mutant killed by [sigabrt] case only, timeout-only mutant still killed (reviewer)

## Test (tester)
- 2026-11-07 — Clean clone of HEAD 5c531b6 plus only working-tree tests/test_corpus.py (AFL-005 WIP excluded), repo .venv.
- Gates: `ruff check .` all passed; `mypy src` no issues (8 files); `pytest` 32 passed; tests/test_corpus.py 12 passed incl. `[sigsegv]`, `[sigabrt]`, `[hang]`.
- AC1–3: ABORT fixture uses `signal.SIGABRT`, sits in the parametrize list, checks `outcome == "crash"`, and runs the same raise + unchanged-state assertions as SIGSEGV.
- AC4 mutant `signal == SIGSEGV or timed_out`: only `[sigabrt]` fails, so killed. Timeout-only mutant: `[sigsegv]`, `[sigabrt]`, `[hang]` fail, still killed. Original corpus.py passes.
- AC5: `git diff --stat` for AFL-017 is tests/test_corpus.py only (+8/−3); corpus.py and executor.py unchanged.
- Note: the leftover second SIGSEGV observe() in the test is redundant but harmless (allowed by the architect note).
- Scratch clone discarded. Verdict: GREEN, ready for crew-lead close.
- 2026-11-07 — DoD verified, closed (orchestrator/crew-lead): ACs checked, reviewer approve, tester green, gates green
