---
id: AFL-042
title: Simplify the README and tidy the repo (widened, lead decision, 2026-11-23)
requirement: submission (lead decision, 2026-11-23)
paper_ref: n/a
module: README.md, CLAUDE.md, tickets/README.md
depends_on: [AFL-041]
status: done
owner: developer
---

## Goal
Replace README.md with the lead's shorter text (lead decision, 2026-11-23), correcting it only where a check against the repo shows a command or claim is wrong. Then tidy the repo per the audit ruling (widened, lead decision, 2026-11-23): fix the stale lines in CLAUDE.md and tickets/README.md. src/, harness/, targets/ and experiments/ stay frozen.

## Acceptance criteria
- [x] README.md is the lead's text, verbatim except for listed corrections, each with its reason.
- [x] Every command, flag, output path and claim in the README is checked against the repo (setup, test counts, build output, demo commands and outputs, campaign flags, analysis outputs, analysis-only re-run, repository bullets).
- [x] Setup and the two demo commands run from an extracted copy of the working tree outside the repo, and the Demo bullets match what they produce.
- [x] Pinned links point to v1.2-submission and return 200 after the push.
- [x] Nothing outside README.md, CLAUDE.md, tickets/README.md and this ticket (plus its INDEX row) changes (widened, lead decision, 2026-11-23).
- [x] The zip is rebuilt from v1.2-submission with the AFL-041 include list and verified (install, build, ruff, mypy, fast tests, line count 7,987); filename, size and SHA-256 are logged here.

## Technical notes (architect)
Same zip include list as AFL-041. The README commit (171b54d) stays as it is; the tidy-up is a second commit on top of it, and the tag v1.2-submission goes on that second commit (lead decision, 2026-11-23); v1.0-submission and v1.1-submission are never moved.

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
- 2026-11-23 README commit made locally (171b54d, not pushed, not tagged). Tag held; ticket widened to "Simplify the README and tidy the repo"; the cleanup goes in with the README and v1.2-submission is tagged once (lead decision, 2026-11-23). Read-only audit of tracked files outside the code directories started.
- 2026-11-23 audit ruling (lead decision, 2026-11-23): apply S1-S5; keep docs/adr/.gitkeep, tickets/done/.gitkeep, .prettierignore, data/SHA256SUMS and results/.gitkeep; leave PRD NFR-4 and the dead links in INDEX.md (historical); no amend: the tidy-up is a second commit on 171b54d and v1.2-submission tags it.
- 2026-11-23 tidy-up applied. CLAUDE.md: §4 campaign command gets `--kind main --freeze-commit ff19bef7abb57b1ccbffd0318e2bbcb3c13f9cfc` (the runner refuses without it); §3 tree: README comment is "setup, demo and reproduction steps", the commands line lists all six commands, and one line each is added for .githooks/commit-msg, data/SHA256SUMS, docs/demo/, docs/report/, .claude/settings.json, .claude/hooks/ and the targets/ files (mini_format.c, cov_rt.c, spike.c, seeds/, ground_truth.json, triggers.json). tickets/README.md: AFL-001..AFL-014 becomes AFL-001..AFL-042. No file deleted; §2 and §7 keep their numbers.
- 2026-11-23 README "How it was built": the sentence "From 14 November, an AI assistant (Claude) made day-to-day lead decisions." is put back after "a small part came in with the first commit." (student's decision, 2026-11-23).
- 2026-11-23 gates after the tidy-up: ruff check . passed; mypy src: no issues in 8 source files; pytest -m "not slow": 607 passed, 10 deselected in 135 s. README "What's in the repository" re-checked: nothing it names was moved or deleted, so it still matches.
- 2026-11-23 the student ran block.sh and tag.sh: the tidy-up commit 59f7811 sits on 171b54d, which sits on d7a59cb; the annotated tag v1.2-submission is on 59f7811; main and the tag reached origin at 2026-11-23T18:24:40Z. On origin, v1.0-submission is still on ad79235 and v1.1-submission on 9ee2326. block.sh confirmed nothing outside README.md, CLAUDE.md and tickets/ changed since d7a59cb, and src/, harness/, targets/ and experiments/ are unchanged since the freeze commit.
- 2026-11-23 orchestrator: the pinned summary link (blob/v1.2-submission/docs/report/summary.md), the clone URL and tree/v1.2-submission return HTTP 200.
- 2026-11-23 orchestrator: zip built from the tag with `git archive --format=zip --prefix=AFLFast-reproducer/` and the AFL-041 include list (nothing in it was deleted, so the list is unchanged). File: AFLFast-reproducer-v1.2-submission.zip, 162,735 bytes, SHA-256 94898f095d7c1ee0d316547c723553e19edd9febf9cfdd3aed4ca92f634ebe8b, 91 files. No report, DETAILS.md, .DS_Store, PDF, results/ or home paths in it.
- 2026-11-23 orchestrator: verified from an extracted copy outside the repo: fresh venv (Python 3.12.9), `pip install -r requirements.txt`, `pip install -e .`, `make -C targets clean all` with Homebrew clang (four targets built), `ruff check .` all checks passed, `mypy src` no issues in 8 source files, `pytest -m "not slow"` 607 passed, 10 deselected in 175 s, rc 0. Line count from the zip: Python 7,624 (36 files), C 327 (5), Makefile and git hook 36 (2), total 7,987. The temp copy was deleted.
- 2026-11-23 DoD verified, moved to done (orchestrator; lead decision, 2026-11-23: closed in a tickets-only follow-up commit; the tag stays on 59f7811)
- 2026-11-23 orchestrator: the gated move printed no hook output, so the gates were re-run after the move: `ruff check .` all checks passed (rc 0); `mypy src` no issues in 8 source files (rc 0); `pytest -m "not slow"` 607 passed, 10 deselected, no failures.
