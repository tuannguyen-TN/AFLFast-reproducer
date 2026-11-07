---
id: AFL-011
title: Campaign runner — N trials × targets × schedules (Klees backbone)
requirement: FR-7
paper_ref: Klees §methodology (repeated trials, fixed budget, seeds)
module: harness/run_campaign.py
depends_on: [AFL-007]
status: backlog
owner: developer
---

## Goal
Run the comparison the way Klees requires: many independent trials per condition,
fixed wall-clock budget, distinct recorded seeds, persisted time-series metrics.

## Acceptance criteria
- [ ] Reads `experiments/configs/main.yaml`.
- [ ] Runs ≥10 trials per (target × schedule); trial i uses `base_seed + i`.
- [ ] Each trial honours `seconds_per_trial` and writes a per-trial metrics file
      (edges-over-time, unique-crashes-over-time, time-to-first-crash).
- [ ] Each result records commit hash + exact command (NFR-1).
- [ ] Re-running a trial with the same seed reproduces its metrics stream.

## Technical notes (architect)
Harness depends on the fuzzer package, never the reverse. Keep statistics OUT of
this file (that is AFL-012); here only orchestrate + persist raw metrics.

## Test approach (tester)
Validity checklist: trial count, distinct seeds, budget honoured, reproducibility
under fixed seed. Flag any Klees anti-pattern (single-run, missing variance).

## Log
- 2026-11-__ — created (req-engineer)
