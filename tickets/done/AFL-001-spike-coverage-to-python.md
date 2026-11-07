---
id: AFL-001
title: Spike — prove coverage bitmap reaches Python (GO/NO-GO)
requirement: FR-1
paper_ref: AFL whitepaper (edge bitmap); enables AFLFast reproduction
module: coverage.py (throwaway spike first)
depends_on: []
status: done
owner: developer
---

## Goal
De-risk the single hardest part before committing: confirm that a C target
compiled with `-fsanitize-coverage=trace-pc-guard` can hand an edge-hit signal to
the Python orchestrator. This gates the whole project.

## Acceptance criteria
- [x] A trivial instrumented C target builds via `make -C targets`.
- [x] One execution from Python yields a **non-empty** set/bitmap of hit edges.
- [x] Two inputs that drive different branches produce **different** edge sets.
- [x] A short note records the mechanism chosen (shared memory vs file) → ADR.

## Technical notes (architect)
Prefer an AFL-style shared-memory bitmap; if that is slow to stand up, a file-based
guard callback is an acceptable spike fallback. Outcome feeds ADR-0001 (coverage
mechanism). If NO-GO, escalate to Vision: pivot to wrapping real AFL and shift
effort to the Klees evaluation layer.

## Test approach (tester)
Manual for the spike: inspect the two differing edge sets. Promote to an automated
integration test once FR-1 lands in AFL-002.

## Log
- 2026-11-__ — created (req-engineer)
- 2026-11-07 — GO decided by human. Edge sets differ: "A"→{1,2}, "B"→{1,3}. Fixes: Homebrew clang (Apple clang 17 ASan hangs on macOS 26.5) and spike built at -O0 (-O1 folds the branch). ADR criterion left for architect.
- 2026-11-07 — ADR-0001 accepted; gates green (ruff, mypy, pytest via .venv); moved to review (orchestrator)
- 2026-11-07 — Review: APPROVE → testing (reviewer). All 4 AC verified: clean `make -C targets` (Homebrew clang) builds spike; spike test passes (not skipped); A→{1,2}, B→{1,3}, repeat-stable; ADR-0001 matches Makefile. ruff/mypy/pytest green. Non-blocking notes in review report.
- 2026-11-07 — Test: PASS → ready to close (tester). Clean copy of working tree (no .git/.venv/bin): `make -C targets` used Homebrew clang 23.1.3, spike at -O0 linked to Homebrew ASan rt; pytest 1 passed (not skipped), mypy clean, ruff clean in repo. Determinism: 10 runs each — "A"→{1,2}, "B"→{1,3}, ""→{1,3}, "AB"→{1,2}, "\xff"→{1,3}, all stable. ADR facts confirmed: spike rebuilt at -O1 gives {1} for both A and B (fold confirmed); ~18-19 execs/sec measured (ADR says ~24; same order), bare process spawn alone is ~18/sec, so ASan process startup, not shm, is the bottleneck (input for AFL-003). Notes: ruff fails on .claude/hooks/*.py when run without .git (hooks are gitignored, so a fresh clone also lacks the DoD hooks); run_with_coverage replaces the whole env (no ASAN_OPTIONS/PATH); toy/tlv targets don't link cov_rt yet (AFL-002).
- 2026-11-07 — DoD verified; closed (crew-lead)
