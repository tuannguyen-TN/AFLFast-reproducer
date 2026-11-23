---
id: AFL-042
title: Simplify the README
requirement: submission (lead decision, 2026-11-23)
paper_ref: n/a
module: README.md
depends_on: [AFL-041]
status: in-progress
owner: developer
---

## Goal
Replace README.md with the lead's shorter text (lead decision, 2026-11-23), correcting it only where a check against the repo shows a command or claim is wrong. README only; src/, harness/, targets/ and experiments/ stay frozen.

## Acceptance criteria
- [x] README.md is the lead's text, verbatim except for listed corrections, each with its reason.
- [x] Every command, flag, output path and claim in the README is checked against the repo (setup, test counts, build output, demo commands and outputs, campaign flags, analysis outputs, analysis-only re-run, repository bullets).
- [x] Setup and the two demo commands run from an extracted copy of the working tree outside the repo, and the Demo bullets match what they produce.
- [ ] Pinned links point to v1.2-submission and return 200 after the push.
- [ ] Nothing outside README.md and this ticket (plus its INDEX row) changes.
- [ ] The zip is rebuilt from v1.2-submission with the AFL-041 include list and verified (install, build, ruff, mypy, fast tests, line count 7,987); filename, size and SHA-256 are logged here.

## Technical notes (architect)
Same zip include list as AFL-041. The tag v1.2-submission goes on the AFL-042 README commit; v1.0-submission and v1.1-submission are never moved.

## Test approach (tester)
Grep the README's commands and paths against the code; run Setup and the demo from an extracted copy; check the pinned links after the push; build and test from the extracted zip.

## Log
- 2026-11-23 created (lead decision, 2026-11-23)
- 2026-11-23 moved to in-progress (developer)
- 2026-11-23 claim check (reviewer, Opus, read-only): commands, flags, output paths, test counts, demo numbers, campaign settings, analysis outputs and repository bullets checked against the code, the config, ADR-0001, PROVENANCE.md and the AFL-039/AFL-041 Logs. Three claims were wrong and seven imprecise; the result line, the crash-reporter commands, the campaign command and the DOIs are correct as written.
- 2026-11-23 Setup, run from an extracted copy of HEAD outside the repo (Python 3.12.9): `make -C targets clean all` built toy_parser, tlv_parser, mini_format and spike into targets/bin/ with Homebrew clang; pytest gave 607 passed, 10 deselected in 134 s.
- 2026-11-23 demo, same copy: both runs exited 0, printed nothing and stopped after 60 s. Final rows: UNIFORM 1,152 execs, 8 edges; FAST 1,113 execs, 7 edges. Each run had 2 crash events and 1 saved crash: crashes/ holds one .bin and one .json, whose `stderr` holds the AddressSanitizer report, crash site `scan`. queue/ holds 4 and 3 inputs.
- 2026-11-23 analysis-only re-run, same copy: the results archive was extracted into an empty folder and its results/ copied in next to results/demo. aggregate.py and plots.py exited 0, and summary.csv, summary.md and trials.csv are byte-identical to docs/report/ (the demo runs are not counted).
- 2026-11-23 README written: the lead's text with seven corrections. (1) Python: macOS's own /usr/bin/python3 is 3.9, below the 3.10 floor in pyproject.toml. (2) The Makefile falls back to `clang` on PATH, not specifically to Apple's clang. (3) crashes/ saves a crash only when its path or crash site is new: the demo had 2 crash events and 1 saved crash per run. (4) The analysis-only copy must go into a clone without results/main/, or the two campaigns' files merge. (5) targets/ also holds the coverage runtime and the spike program, and ground_truth.json maps each bug to its function, not each crash to a bug. (6) The submission zip includes ADR-0003, which tests/test_dedup.py reads. (7) Two tests read .githooks/ and .claude/hooks/, so "none of them is needed to run anything" was not true of the test suite.
- 2026-11-23 lead wording for the crashes/ bullet: a crash is saved only on a new path or crash site, so crashes/ can hold fewer than `tail` counts; each saved crash is a .bin plus a JSON file (matches fuzzer.py crash()).
- 2026-11-23 the student edited "How it was built" and removed the sentence saying an AI assistant made day-to-day lead decisions from 14 November; accepted as the student's edit.
