---
id: AFL-041
title: Submission cleanup and package
requirement: submission (lead decision, 2026-11-21)
paper_ref: n/a
module: README.md, .gitignore, tickets/, docs/report/REPORT.md (removed)
depends_on: [AFL-039, AFL-040]
status: done
owner: developer
---

## Goal
Remove the report from the repo (lead decision, 2026-11-21: the report is submitted to the professor separately), clean the README, do housekeeping (.gitignore, close AFL-019/AFL-021/AFL-029), and build and verify a codebase-only zip. No changes to src/, harness/, targets/ or experiments/.

## Acceptance criteria
- [x] The report is removed from the repo by the human's commit block; a copy outside the repo holds the working-tree report.
- [x] README has no link or pointer into the report.
- [x] Every README link or image into docs/ or tickets/ is an absolute GitHub URL pinned to v1.1-submission (blob for links, raw for images).
- [x] README carries the AI-use disclosure verbatim, the H1-not-supported line with a pointer to the committed summary, and the .claude/ and CLAUDE.md line.
- [x] .gitignore covers .venv/, __pycache__/, .pytest_cache/, .mypy_cache/, .ruff_cache/, .coverage, htmlcov/, target build outputs, raw results, .DS_Store, *.tar.gz, docs/papers/*.pdf, .claude/settings.local.json; `git ls-files -ci --exclude-standard` prints nothing.
- [x] AFL-019, AFL-021 and AFL-029 are closed in tickets/done/ and INDEX.md is consistent.
- [x] `ruff check .`, `mypy src` and `pytest` pass.
- [x] The zip is built with `git archive` at tag v1.1-submission, contains no docs/ or tickets/ (except tickets/templates/ticket-template.md), and is verified.

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
- 2026-11-21 orchestrator: commit 9ee2326 (AFL-041) and annotated tag v1.1-submission (tag object a1b5752) were made and pushed by the human; `git ls-remote origin` shows refs/heads/main and refs/tags/v1.1-submission^{} both at 9ee23262c097d8f4ba307c6a843c0d1d855b58cc, and v1.0-submission^{} still at ad79235. The human pushed at 2026-11-22T00:33:31Z (UTC).
- 2026-11-21 orchestrator: zip built from the tag with `git archive --format=zip --prefix=AFLFast-reproducer/` and the lead's include list (.claude/agents, .claude/commands, .claude/hooks, .claude/settings.json, .githooks, .gitignore, CLAUDE.md, README.md, pyproject.toml, requirements.txt, src, harness, targets, experiments, tests, tickets/templates/ticket-template.md, docs/adr/0003-crash-site-dedup.md). File: AFLFast-reproducer-v1.1-submission.zip, 163,992 bytes, SHA-256 b0eef7e33421b92a6befe2d168b52ac9b1b9c5df198aa3cbddc54eeb3da0d28b, 91 files. `unzip -l` shows no report, DETAILS.md, settings.local.json, .DS_Store, PDF, tar.gz, data/, results/, docs/ (other than the ADR) or tickets/ (other than the template).
- 2026-11-21 orchestrator: verified from an extracted copy outside the repo with the README steps: fresh venv (Python 3.12.9), `pip install -r requirements.txt`, `pip install -e .`, `make -C targets clean all` with Homebrew clang (four targets built), `ruff check .` all checks passed, `mypy src` no issues in 8 source files, `pytest -m "not slow"` 607 passed, 10 deselected, rc 0; nothing needed results/ to exist. Line count from the zip: Python 7,624 (36 files), C 327 (5), Makefile and git hook 36 (2), total 7,987. All 8 pinned v1.1-submission links and images in the README return HTTP 200. The temp copy was deleted.
- 2026-11-21 DoD verified, moved to done (orchestrator; lead decision, 2026-11-21: closed in a tickets-only follow-up commit; the tag stays on 9ee2326)
- 2026-11-21 orchestrator: the gated move printed no hook output, so the gates were re-run after the move: `ruff check .` all checks passed (rc 0); `mypy src` no issues in 8 source files (rc 0); `pytest -m "not slow"` 607 passed, 10 deselected, no failures.
