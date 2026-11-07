---
id: AFL-001
title: Spike — prove coverage bitmap reaches Python (GO/NO-GO)
requirement: FR-1
paper_ref: AFL whitepaper (edge bitmap); enables AFLFast reproduction
module: coverage.py (throwaway spike first)
depends_on: []
status: backlog
owner: developer
---

## Goal
De-risk the single hardest part before committing: confirm that a C target
compiled with `-fsanitize-coverage=trace-pc-guard` can hand an edge-hit signal to
the Python orchestrator. This gates the whole project.

## Acceptance criteria
- [ ] A trivial instrumented C target builds via `make -C targets`.
- [ ] One execution from Python yields a **non-empty** set/bitmap of hit edges.
- [ ] Two inputs that drive different branches produce **different** edge sets.
- [ ] A short note records the mechanism chosen (shared memory vs file) → ADR.

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
