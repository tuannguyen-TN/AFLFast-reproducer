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
- [ ] Per-trial metrics also record `distinct_path_ids` (count of distinct
      `coverage.path_id` values over all execs) and `corpus_size`, both final and
      over time.
- [ ] **Pilot + coverage-granularity fallback (pre-registered, ADR-0001).** A pilot
      mode runs 3 trials per (target × schedule) at the main `seconds_per_trial`, with
      seeds `base_seed + 1000 + i` (disjoint from main trials), writing to
      `results/pilot/`; pilot results are excluded from AFL-012 analysis. Decision
      rule, evaluated on the pilot before the main campaign, pooled over both arms,
      per target:
      - **Trigger:** median `distinct_path_ids` < 2 × median final `corpus_size`,
        OR median `distinct_path_ids` < 20.
      - If the trigger fires on any target: switch the whole experiment (both arms,
        all targets) to AFL hit-count buckets via the AFL-002 seam (`cov_rt.c` u8
        saturating counts + bucketing in `coverage.py`; no other module changes),
        through a new ticket, then re-run the pilot once to record the new numbers.
      - If not: stay presence-only.
      - Either way, the runner writes the pilot medians, the trigger result and the
        chosen granularity to `results/pilot/granularity_decision.json`, and the
        decision is recorded in ADR-0001. Thresholds may change only before the
        pilot runs, never after seeing it (no post-hoc tuning).

## Technical notes (architect)
Harness depends on the fuzzer package, never the reverse. Keep statistics OUT of
this file (that is AFL-012); here only orchestrate + persist raw metrics.
The pilot rule is a fixed threshold on two medians, not a statistic, so it stays here.
`distinct_path_ids` has to come from the fuzzer loop's metrics (AFL-007): it keeps a
set of `path_id`s seen. Under presence-only every retained seed has a unique path, so
"distinct paths ≈ corpus size" means f(i) barely exceeds the seed's own fuzzing and
FAST cannot separate rare from frequent paths. That is what the trigger detects.
Granularity is never an arm-level knob: both arms always share it (NFR-2).

## Test approach (tester)
Validity checklist: trial count, distinct seeds, budget honoured, reproducibility
under fixed seed. Flag any Klees anti-pattern (single-run, missing variance).

## Log
- 2026-11-__ — created (req-engineer)
- 2026-11-07 — added distinct_path_ids metric and pre-registered pilot fallback
  (presence-only → hit-count buckets) per human decision; see ADR-0001 (architect)
