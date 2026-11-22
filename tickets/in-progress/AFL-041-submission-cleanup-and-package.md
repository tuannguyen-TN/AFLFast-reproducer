---
id: AFL-041
title: Submission cleanup and package
requirement: submission (lead decision, 2026-11-21)
paper_ref: n/a
module: README.md, .gitignore, tickets/, docs/report/REPORT.md (removed)
depends_on: [AFL-039, AFL-040]
status: in-progress
owner: developer
---

## Goal
Remove the report from the repo (lead decision, 2026-11-21: the report is submitted to the professor separately), clean the README, do housekeeping (.gitignore, close AFL-019/AFL-021/AFL-029), and build and verify a codebase-only zip. No changes to src/, harness/, targets/ or experiments/.

## Acceptance criteria
- [ ] The report is removed from the repo by the human's commit block; a copy outside the repo holds the working-tree report.
- [ ] README has no link or pointer into the report.
- [ ] Every README link or image into docs/ or tickets/ is an absolute GitHub URL pinned to v1.1-submission (blob for links, raw for images).
- [ ] README carries the AI-use disclosure verbatim, the H1-not-supported line with a pointer to the committed summary, and the .claude/ and CLAUDE.md line.
- [ ] .gitignore covers .venv/, __pycache__/, .pytest_cache/, .mypy_cache/, .ruff_cache/, .coverage, htmlcov/, target build outputs, raw results, .DS_Store, *.tar.gz, docs/papers/*.pdf, .claude/settings.local.json; `git ls-files -ci --exclude-standard` prints nothing.
- [ ] AFL-019, AFL-021 and AFL-029 are closed in tickets/done/ and INDEX.md is consistent.
- [ ] `ruff check .`, `mypy src` and `pytest` pass.
- [ ] The zip is built with `git archive` at tag v1.1-submission, contains no docs/ or tickets/ (except tickets/templates/ticket-template.md), and is verified.

## Technical notes (architect)
Zip include list: code, tests, build/config files, README, .claude/ (no settings.local.json), .githooks/, CLAUDE.md and the ticket template; not docs/ (except what a test reads), tickets/, data/ or results/. docs/report/figures/, summary.csv, summary.md, trials.csv, PROVENANCE.md and docs/demo/ stay in the repo. A copy of the working-tree report is kept outside the repo.

## Test approach (tester)
Grep README for report pointers and non-absolute docs/tickets links; run `git ls-files -ci --exclude-standard`; list the zip contents and build/test from an extracted copy.

## Log
- 2026-11-21 created (lead decision, 2026-11-21: the report leaves the repo and is submitted to the professor separately; ID AFL-041 because AFL-040 is already used by the condense ticket)
- 2026-11-21 moved to in-progress (developer)
- 2026-11-21 developer: README edited (pointers to the report removed, docs/ links and images made absolute v1.1-submission URLs, result line, AI-use disclosure, .claude line, clone-not-zip note); .gitignore gained .ruff_cache/ and *.tar.gz; AFL-019/021/029 closed into tickets/done/; INDEX.md updated; AFL-040 Log appended. Report removal, tag and zip remain open.
- 2026-11-21 orchestrator: README result line corrected to the pre-registered H1 definition (no primary endpoint at Holm-adjusted p < 0.05; all adjusted p = 1, per docs/report/summary.md). The gated moves of AFL-019/021/029 printed no hook output, so the gates were re-run: `ruff check .` all checks passed; `mypy src` no issues in 8 source files; `pytest -m "not slow"` 607 passed, 10 deselected, rc 0. Nothing in tests, hooks, scripts or config reads REPORT.md (only README pointed to it). Zip finding: tests/test_dedup.py:95 reads docs/adr/0003-crash-site-dedup.md, so that one file must be in the zip or one test fails (lead to rule). Line counts at HEAD match a23c569: Python 7,624, C 327, Makefile and git hook 36, total 7,987.
- 2026-11-21 orchestrator: README intro reworded (lead decision, 2026-11-21): it now says the project tests whether AFLFast's power schedule (FAST) beats a uniform schedule, instead of claiming it reproduces the advantage; the "What it reproduces" bullet became "What it tests". Lead rulings: docs/adr/0003-crash-site-dedup.md is in the zip; .prettierignore, data/SHA256SUMS and results/.gitkeep stay out; DETAILS.md stays untracked; AFL-041 closes in a tickets-only follow-up commit after the zip is verified, with the zip filename, size and SHA-256 logged here.
