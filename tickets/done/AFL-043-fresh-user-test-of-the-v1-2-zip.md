---
id: AFL-043
title: Fresh-user test of the v1.2 zip
requirement: submission (lead decision, 2026-11-23)
paper_ref: Klees §5 (reproducibility)
module: none (testing only; README fixes proposed, not applied)
depends_on: [AFL-042]
status: done
owner: tester
---

## Goal
Test the v1.2 submission end to end as a new user would (lead decision, 2026-11-23): the zip's README followed by a fresh agent with no project context, an exact analysis-only reproduction from a fresh clone, and a full campaign re-run on the lead's go-ahead. Testing only: no commits, no repo edits beyond this ticket and its INDEX row, nothing proposed is applied until the lead rules.

## Acceptance criteria
- [x] The zip on the Desktop matches the SHA-256 logged in AFL-042.
- [x] Phase A: a fresh agent, given only the zip path and the lead's instruction, follows Requirements, Setup and the Demo from the README alone; each step is recorded with its command, pass/fail, time, whether the output matched the README, and anything unclear.
- [x] Phase B: in a fresh clone at v1.2-submission, Setup and the "Re-run only the analysis" path are run on a copy of the raw results archive; cmp's result and byte-identity of summary.md, trials.csv and the six figures are reported; the report's key numbers are checked against the regenerated summary.
- [ ] Phase C (on the lead's go-ahead, crash reporters off by the lead): README step 3 is run in the fresh clone, then aggregate.py and plots.py; each measure is compared with docs/report/ and whether the conclusion holds is stated. Not done (lead decision, 2026-11-23): Phase C is optional and gets a new ticket if it is ever run.
- [x] Newcomer friction points are listed worst first, each with a proposed one-line README fix (not applied). The lead's rulings on them became AFL-044.
- [ ] Temp folders are deleted at the end, except the Phase C results folder, which stays until the lead has seen the comparison. Not done at close (lead decision, 2026-11-23): Phase A's folders and Phase B's archive copy are deleted; the Phase B clone and the measurement runs are kept until the v1.3 zip is verified, and their deletion is logged in AFL-044.

## Technical notes (architect)
All work happens in a new temp folder outside the repo. The original raw results archive is never modified or moved; Phase B uses a copy. The Phase A agent must not read CLAUDE.md, tickets/ or the main repo; where the README leaves it stuck, that is a finding, noted before any workaround.

## Test approach (tester)
Phase A is a scripted walkthrough by an agent with no project brief. Phase B checks byte-identity with cmp and the numbers against summary.md. Phase C compares per measure: median [IQR], A12, Holm-adjusted p, and hard-bug counts and times.

## Log
- 2026-11-23 created (lead decision, 2026-11-23)
- 2026-11-23 moved to in-progress (tester)
- 2026-11-23 orchestrator: ~/Desktop/AFLFast-reproducer-v1.2-submission.zip SHA-256 is 94898f095d7c1ee0d316547c723553e19edd9febf9cfdd3aed4ca92f634ebe8b, matching AFL-042. The raw results archive's SHA-256 matches the last line of data/SHA256SUMS.
- 2026-11-23 Phase A (fresh Sonnet agent, brief: the zip path, the lead's instruction, the scope and the safety rules only; Claude Code may still load the project CLAUDE.md into a subagent automatically, so "no project context" is as far as the brief goes): Requirements present (macOS 26.5 arm64, python3 3.12.9, Homebrew clang); venv, `pip install -r requirements.txt` (26 s), `pip install -e .` (4 s), `make -C targets clean all` (1 s, Homebrew clang, four targets) and `pytest` (607 passed, 10 deselected, 181 s; README says about 2 minutes) all passed. Both demo runs exited 0 and printed nothing, but gave 474 and 427 executions, 6 edges each and 0 crashes, so crashes/ was never created (README: 1,169 and 937 executions, 7-8 edges, crashes in scan()). The machine was busy (load average about 4.5: WindowServer, a browser, cameracaptured).
- 2026-11-23 orchestrator, demo check in the same copy: UNIFORM with seed 7000 for 60 s again gave 432 executions and 0 crashes; for 180 s it gave 1,268 executions, 8 edges, 2 crash events and 1 saved crash, the first at execution 614 (92 s), site scan. The mutant sequence is fixed by the seed, so a 60 s demo crashes only if it reaches about 614 executions (about 10 per second); the AFL-042 run on an idle machine reached 1,152.
- 2026-11-23 Phase B, fresh clone at v1.2-submission (HEAD 59f7811, full history; cloned with `git clone --branch v1.2-submission`, equivalent to the README's clone and checkout): Setup passed (607 passed, 10 deselected, 179 s). A copy of the raw results archive (SHA-256 matches data/SHA256SUMS) was extracted into an empty folder and its results/ copied into the clone; aggregate.py and plots.py exited 0. cmp printed "summary.csv identical"; summary.md, trials.csv and all six figures are byte-identical to docs/report/. Every key number checked (final edges medians and IQRs, hard-bug find rates, Holm-adjusted p = 1, smallest raw p 0.5129, the six primary A12s, easy bugs 27 vs 30, mini_format unique-crash p 0.07672) matches. The original archive was not modified or moved. Phase A's folder and Phase B's archive copy and extraction were deleted.
- 2026-11-23 lead: Phase B accepted; the report's numbers reproduce byte for byte. Phase C on hold; the Phase B clone is kept until the lead decides on the overnight run. README fixes moved to AFL-044 (lead decision, 2026-11-23).
- 2026-11-23 lead: close AFL-043 in the AFL-044 commit. Phase B accepted; Phase C not run (optional; a new ticket if it is ever done). The Phase B clone and the measurement runs are deleted after the v1.3 zip is verified (lead decision, 2026-11-23).
- 2026-11-23 moved to done (crew-lead, via the gated mv)
- 2026-11-23 gates after the gated mv (the hook printed no output, so re-run and logged): ruff check . (All checks passed), mypy src (no issues, 8 files), pytest -m "not slow" (607 passed, 10 deselected in 111 s).
