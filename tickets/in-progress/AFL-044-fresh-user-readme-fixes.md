---
id: AFL-044
title: Fresh-user README fixes
requirement: submission (lead decision, 2026-11-23)
paper_ref: n/a
module: README.md
depends_on: [AFL-043]
status: in-progress
owner: developer
---

## Goal
Fix the README friction found by the AFL-043 fresh-user test (lead decision, 2026-11-23). README only; frozen code (src/, harness/, targets/, experiments/) untouched. Each fix replaces a line or adds one line, so the README stays as short as it is.

## Acceptance criteria
- [x] Demo length: the execution at which seed 7000 first crashes is measured for both schedules; `--seconds` in each demo command lets that schedule reach its first crash at 5 executions per second, rounded up to a whole minute. The seed is unchanged. Both runs then set to the same 180 s (lead decision, 2026-11-23).
- [x] Expected results: the single example run is replaced by what should match and what varies: edges (the observed range), the crash (in `scan()`, toy_parser's easy bug) and executions (a rough range that depends on machine load). Only measured figures are used.
- [x] The `tail` line is replaced by a command that prints each file's header above its last row, aligned; one bullet defines only the columns a reader needs (executions, edges, crash events vs saved crashes, corpus size), under their real names.
- [x] pytest: "about 2 minutes" becomes "about 3 minutes".
- [x] Requirements: "Check with python3 --version. If it's below 3.10, run brew install python@3.12 and use python3.12 in the first Setup command." (`python3.12` confirmed as the command Homebrew installs.)
- [x] Build check: make prints the full compiler path, so the README says the clang lines should start with /opt/homebrew/opt/llvm/. No Makefile change.
- [x] Setup: "The zip unzips to AFLFast-reproducer/; run everything from inside it."
- [x] Phase A re-run by a fresh agent on a zip of the same include list built from the working tree: both demo runs produce a crash and the expected-output bullets match what it sees.
- [x] ruff, mypy and pytest -m "not slow" pass.

## Technical notes (architect)
Skipped by ruling: the pip notice, the .dSYM folders and run.json's "unknown" commit. The mutant sequence is fixed by the seed, so the execution of the first crash does not depend on machine load; wall-clock time only limits how many executions run.

## Test approach (tester)
Measure the first-crash execution per schedule from crash_events.csv; re-run Phase A from a fresh zip; gates.

## Log
- 2026-11-23 created from the AFL-043 findings (lead decision, 2026-11-23)
- 2026-11-23 moved to in-progress (developer)
- 2026-11-23 orchestrator: Homebrew's python@3.12 caveat (`brew info python@3.12`) says it installs as /opt/homebrew/bin/python3.12. make prints the full compiler path (/opt/homebrew/opt/llvm/bin/clang …).
- 2026-11-23 orchestrator, measurements (Phase B clone at v1.2-submission, toy_parser, seed 7000, timeout 5, load average 3-4): 600 s runs put the first crash at execution 614 for UNIFORM (72 s) and 588 for FAST (70 s), both in scan(). At 5 executions per second that is 122.8 s and 117.6 s, so `--seconds 180` for UNIFORM and `--seconds 120` for FAST. Edges by execution: UNIFORM 6 from 148, 8 from 789, 9 from 1,297; FAST 6 from 148, 7 from 881, 8 from 3,680. In the 600 s runs UNIFORM reached 9 edges at 148 s and FAST 7 at 98 s, both inside the new demo lengths. The demo commands at the new lengths gave UNIFORM 1,286 executions, 8 edges, 2 crash events, 1 saved crash; FAST 875 executions, 6 edges, 2 crash events, 1 saved crash (about 7 executions per second each). All 31 crash events across the four runs are in scan(). Rates measured so far: 7 to 19 executions per second (19 on an idle machine in the AFL-042 demo).
- 2026-11-23 developer (Sonnet): applied the README edits, README only; 102 to 103 lines (one added line, the Python check; every other fix replaces a line in place). Also, in the orchestrator's brief: the pinned summary link and the clone step's checkout now name v1.3-submission, so a new user lands on the README with these fixes. The display command was tested in zsh and bash on the measured demo output.
- 2026-11-23 Phase A re-run: a fresh Sonnet agent got a zip of the same 91-path include list built from the working tree (README byte-identical to the working tree) and followed the README. It stopped once when a command was denied: the agent had added its own redirect to /tmp, not a README step. It resumed with the README commands as written. Setup: venv, both pip installs, make (four clang lines starting /opt/homebrew/opt/llvm/bin/clang), pytest 607 passed, 10 deselected in 167 s. Demo (load average 3.4 to 2.4): UNIFORM 180 s, 1,539 executions, 9 edges, 3 crash events, 1 saved; FAST 120 s, 972 executions, 7 edges, 2 crash events, 1 saved; crashes/ in both. First crashes at executions 614 and 588 again. Every crash event is in scan(); ASan reports a heap-buffer-overflow READ of size 1 in scan(). Edges, the crash and the rate (8.5 and 8.1 per second) fall inside the README's bullets. The agent's clarity note: "a busy Mac gave 1,286 for UNIFORM and 875 for FAST" doesn't say these are totals (proposed, not applied).
- 2026-11-23 gates: ruff check . (All checks passed), mypy src (no issues, 8 files), pytest -m "not slow" (607 passed, 10 deselected in 130 s).
- 2026-11-23 lead review: approved, including the v1.3-submission link and checkout. Changes (lead decision, 2026-11-23): both demo runs at --seconds 180; drop the "busy Mac" example and keep only the rate range; close AFL-043 in the same commit.
- 2026-11-23 orchestrator: the FAST demo command at --seconds 180 (Phase B clone, load average 5.8 to 2.5) gave 3,715 executions (about 21 per second), 8 edges, 13 crash events and 1 saved crash. Every crash is in scan() (ASan: READ of size 1); the first is at execution 588 again. Edges by execution match the earlier data: 6 from 148, 7 from 881, 8 from 3,680 (reached at 178 s). At 180 s FAST ends at 7 edges below about 20 executions per second and 8 above, so the bullet says 7–8; UNIFORM stays 8–9. The rate range becomes 7 to 21 per second. README: the Demo heading says 3 minutes, the FAST command uses --seconds 180, the first Demo bullet says "stops after 3 minutes (about 6 minutes for both)", and the expected-results bullet drops the busy-Mac example. Still 103 lines.
- 2026-11-23 gates after AFL-043 moved to done (the hook printed no output, so re-run and logged): ruff check . (All checks passed), mypy src (no issues, 8 files), pytest -m "not slow" (607 passed, 10 deselected in 111 s).
