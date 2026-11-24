---
id: AFL-045
title: Keep the Mac awake during the campaign
requirement: submission (lead decision, 2026-11-23)
paper_ref: n/a
module: README.md
depends_on: [AFL-044]
status: done
owner: developer
---

## Goal
Keep the Mac awake during a README reproduction of the main campaign, as the main campaign on ff19bef was run (lead decision, 2026-11-23). README only; frozen code (src/, harness/, targets/, experiments/) untouched.

## Acceptance criteria
- [x] README step 3 prefixes the campaign command with `caffeinate -i`.
- [x] Step 3 gains the line: "caffeinate keeps the Mac awake: a sleep would silently shorten trials, because each one stops on wall-clock time. Leave the Mac otherwise idle while it runs."
- [x] Checked without running the campaign: `caffeinate -i` passes the exit code through, and the `--freeze-commit` check behaves the same under it.
- [x] The header line of a demo metrics.csv and its column order are reported to the lead (read-only).
- [x] ruff, mypy and pytest -m "not slow" pass.
- [x] v1.4-submission tagged and pushed (older tags unmoved); ~/Desktop/AFLFast-reproducer-v1.4-submission.zip built from the tag and verified as for v1.3.

## Technical notes (architect)
`caffeinate -i` stops idle sleep for as long as its child runs and returns the child's exit status. It does not stop sleep from closing the lid.

## Test approach (tester)
Exit codes through caffeinate; runner refusals with and without caffeinate compared; the passing freeze path checked without launching trials; gates; zip verified from an extracted copy.

## Log
- 2026-11-23 created (lead decision, 2026-11-23)
- 2026-11-23 moved to in-progress (developer)
- 2026-11-23 orchestrator, checks on a clean tree at 0ad891f, no campaign launched: `caffeinate -i sh -c 'exit N'` returned N for 0, 1, 2, 3 and 42, and `caffeinate -i false` returned 1. Runner refusals with and without `caffeinate -i` gave the same exit code (2) and byte-identical output, for an unresolvable freeze commit (0000000) and for the first commit (d258fd7, "targets/ or main.yaml changed since freeze commit"). The passing path under `caffeinate -i`: `resolve_freeze_commit('ff19bef')` returned ff19bef7abb57b1ccbffd0318e2bbcb3c13f9cfc, and `git diff --quiet ff19bef… HEAD -- targets/ experiments/configs/main.yaml` exited 0. The tree was still clean afterwards and no runner or fuzzer process was left.
- 2026-11-23 orchestrator: the demo metrics.csv header (results/demo/uniform and fast, matching METRICS_COLUMNS in src/fuzzer/fuzzer.py) is `elapsed_s,execs,edges,corpus_size,distinct_path_ids,crash_events,crashes_saved,hangs,hang_time_s`.
- 2026-11-23 developer (orchestrator): README step 3 edited (the prefix, and one added line); the pinned summary link and the clone step's checkout now name v1.4-submission. README 103 to 104 lines.
- 2026-11-23 gates: ruff check . (All checks passed), mypy src (no issues, 8 files), pytest -m "not slow" (607 passed, 10 deselected in 109 s).
- 2026-11-23 lead review: approved, including the v1.4-submission link and checkout. Committed as 7531935, tagged v1.4-submission and pushed by the user; origin main and v1.4-submission point to 7531935, and v1.0 to v1.3 are unmoved on origin. The pinned summary link returns 200.
- 2026-11-23 zip: AFLFast-reproducer-v1.4-submission.zip built from the tag with git archive and the AFL-041 include list, the same 91 paths as v1.3; 163,051 bytes, SHA-256 fabf64070f741fdd84264c721df1bdfd1a972ee3fe42e2ad55eec1981fc78048. From an extracted copy: no .DS_Store, docs/papers, results/ or home paths; README identical to the repo's; line count 7,987 (Python 7,624 in 36 files, C 327 in 5, Makefile and commit-msg hook 36); fresh venv, both pip installs, make -C targets clean all (four clang lines starting /opt/homebrew/opt/llvm/bin/clang), ruff, mypy, pytest -m "not slow" (607 passed, 10 deselected in 135 s). The extracted copy was deleted afterwards.
- 2026-11-23 closed (crew-lead, lead decision, 2026-11-23)
- 2026-11-23 moved to done with the gated mv; the hook printed nothing, so the gates were re-run: ruff check . (All checks passed), mypy src (no issues, 8 files), pytest -m "not slow" (607 passed, 10 deselected in 110 s).
