---
id: AFL-038
title: Trigger tests use the campaign timeout; README crash-reporter note
requirement: NFR-1 (reproducibility)
paper_ref: n/a
module: tests/test_toy_parser.py, tests/test_tlv_parser.py, tests/test_mini_format.py, tests/test_dedup.py, tests/test_fuzzer.py, tests/test_executor.py (reviewer ruling), README.md
depends_on: [AFL-011, AFL-032]
status: done
owner: developer
---

## Goal
With both macOS crash reporters back on (AFL-011 Log, 2026-11-17),
`tests/test_tlv_parser.py::test_trigger_table` flaked (a hang instead of a crash):
the target-trigger tests use the Executor's default timeout of 1.0 s and the
reporter delays the crash. Give those tests the campaign's timeout, and record in
the README that the campaign ran with the reporters off.

## Acceptance criteria
- [x] (a) In the target-trigger tests (listed in the technical notes) the executor
      timeout is raised from 1 s to the campaign's 5.0 s
      (`experiments/configs/main.yaml`, `timeout_s`). Test files only: nothing under
      `targets/`, `src/`, `harness/` or `experiments/` changes (frozen paths since
      ff19bef). Assertions are otherwise unchanged. Full
      `ruff check . && mypy src && pytest` passes with both reporters on.
- [x] (b) README states: the main campaign ran with both macOS crash reporters (the
      per-user agent `com.apple.ReportCrash` and the system daemon
      `com.apple.ReportCrash.Root`) off; why (they cost CPU on every crash and could
      penalise the arm that crashes more; AFL's own `afl-fuzz` asks for crash
      reporting off on macOS); how to turn them off and back on, using the commands
      recorded in AFL-011's Log (2026-11-15 "crash reporters off" and "reporters-off
      evidence" entries: `launchctl disable` + `bootout` for off; `launchctl enable`
      + `bootstrap` of the two plists for on; the system daemon needs sudo); and that
      a re-run with them on may differ.

## Technical notes (architect)
Executor signature: `Executor(target, timeout_s)`; the default is 1.0 s.
(a) Files and functions (found by reading the tests):
- `tests/test_toy_parser.py`, `tests/test_tlv_parser.py`, `tests/test_mini_format.py`:
  each has a module-scoped fixture `ex` that builds `Executor(TARGETS / "bin" / ...)`
  with the default timeout. Passing `timeout_s=5.0` there (one line per file) covers
  every test that takes `ex`:
  - toy_parser: `test_benign_and_seed_clean`, `test_toy1_deep`, `test_toy2_shallow`,
    `test_single_byte_sweep`.
  - tlv_parser: `test_trigger_table` (the flaky one), `test_benign_and_guard_sides`,
    `test_tlv1_shallow`, `test_tlv2_deep_staircase`, `test_tlv2_oob_boundary`,
    `test_single_byte_sweep`.
  - mini_format: `test_path_diversity`, `test_trigger_table`, `test_mfp2_shallow`,
    `test_mfp1_deep_staircase`, `test_single_byte_sweep`.
- `tests/test_dedup.py::test_crash_site_process_invariant` (line ~116) runs toy-2's
  trigger through `Executor(ROOT / "targets/bin/toy_parser")`: same change.
- `tests/test_fuzzer.py::test_fixture_not_stale` (line ~396) runs a tlv_parser crash
  through `Executor(TARGETS / "bin/tlv_parser")`: same change.
- Developer to check: `tests/test_executor.py` lines ~84, ~121, ~155 (`Executor(toy)`,
  `Executor(target)`). Change them only if they execute a planted bug's trigger and
  rely on the default timeout; tests that deliberately test the default or short
  timeouts stay as they are. `tests/test_retune_odds.py` already uses `timeout_s=5.0`.
(b) README: add the note next to the existing crash-reporter sentence in the
Quickstart ("It ran with the macOS crash reporters turned off; see AFL-011's Log ...",
after the campaign command block). Do not put any absolute home path in the README.

## Test approach (tester)
Run the full `ruff check . && mypy src && pytest` (and `pytest -m slow`) with both
reporters on, several times, and confirm no hang-instead-of-crash flake in the trigger
tests. `git diff --stat` shows only the listed test files and README.md. README
commands match AFL-011's Log text.

## Log
- 2026-11-17 — created (req-engineer), lead decision, 2026-11-17: with both crash reporters back on, `test_tlv_parser.py::test_trigger_table` flaked; trigger tests move to the campaign's 5.0 s timeout and README records the reporters-off campaign condition
- 2026-11-17 — implemented (developer): `timeout_s=5.0` added to the Executor in the `ex` fixtures of test_toy_parser.py, test_tlv_parser.py, test_mini_format.py, and in test_dedup.py::test_crash_site_process_invariant and test_fuzzer.py::test_fixture_not_stale; also the `ex` fixture in test_executor.py (line 84), because `test_asan_crash_despite_parent_env` runs toy-1's trigger ("BUG") and relied on the default; test_executor.py lines ~121 and ~155 left as they are (they do not run a trigger: a clean exit-86 check and a script target). No assertion changed. README Quickstart: crash-reporter note with the off/on commands from AFL-011's Log. Gates with both reporters on: trigger-test files 3 runs x 18 passed; `ruff check .` all checks passed; `mypy src` no issues in 8 files; `pytest` 607 passed, 10 deselected (110.97 s)
- 2026-11-17 — review APPROVED (reviewer): (a) six one-line `timeout_s=5.0` changes, each Executor runs a crash trigger (toy-2 `!aaa`, tlv `A`+len100, `ex` fixtures of toy/tlv/mini, test_executor `ex` via toy-1 "BUG" in test_asan_crash_despite_parent_env: in scope, same defect); test_executor lines 106/121/155 correctly untouched (no trigger); grep finds no other trigger Executor; `git diff --stat -- src targets experiments harness` empty; no assertion changed. (b) launchctl on-commands match the AFL-011 Log character for character (gui/501 -> gui/$(id -u)); off-commands match the Log's described disable+bootout for both services; PRD quote matches docs/PRD.md; no home/scratch paths added. ruff, mypy src, and the six touched test files pass. README claims on AFL check_crash_handling() and AFL++ docs/INSTALL.md are pending the lead's source check
- 2026-11-17 — testing PASS (tester), reporters on (`launchctl print gui/$(id -u)/com.apple.ReportCrash` exit 0): diff scope as listed (README + six tests + the three report tickets; `git diff --stat -- src targets experiments harness` empty; tests diff = exactly six `+timeout_s=5.0` lines, no assertion changed); `ruff check .` all checks passed; `mypy src` no issues in 8 files; `pytest` 607 passed, 10 deselected (110.35 s); `pytest -m slow` 10 passed, 607 deselected (980.27 s); six touched files 3 runs x `92 passed, 4 deselected` (71.97 s, 72.43 s, 71.48 s), no hang-instead-of-crash (these 3 runs overlapped the slow run, so ran under extra CPU load); hygiene grep for /Users/, .claude/jobs, /private/tmp in README+tests additions empty; no campaign running. Status left `testing` (template enum has no ready-to-close value); orchestrator to do the gated close
- 2026-11-17 — source check (Opus reviewer, read-only fetch approved by the lead, lead decision, 2026-11-17): the README claims were checked against github.com/mboehme/aflfast `afl-fuzz.c` `check_crash_handling()` (commit d1d54ca) and github.com/AFLplusplus/AFLplusplus `docs/INSTALL.md` macOS section (commit d798677). One fix: the check matches only the per-user `com.apple.ReportCrash` agent (its pattern cannot match `.Root`), not "a ReportCrash service"; the README now says so, names AFLFast as the copy checked, and gives AFL's own reason (the reporter's delay can make crashes look like timeouts). The AFL++ sentence was confirmed. Prose only; no command or test changed (orchestrator)
- 2026-11-17 — DoD verified; closed via the gated mv (orchestrator)
- 2026-11-17 — after the close (prose only): the README crash-reporters sentence reordered on the AI reviewer pass, so the `AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES` condition sits next to "refuses to run" and the timeout reason follows it; no fact, command or test changed (orchestrator)
