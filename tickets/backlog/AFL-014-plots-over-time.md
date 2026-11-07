---
id: AFL-014
title: Plots — coverage/crash over time + variance
requirement: FR-8
paper_ref: Klees § statistically sound comparisons (report variance across trials, not single runs)
module: harness/plots.py
depends_on: [AFL-011]
status: backlog
owner: developer
---

## Goal
Plot per-trial metrics over time so that the spread between trials is visible
(FR-8, SC5). Each plot shows a median line and an inter-trial variance band for
each arm, never a single run.

Open questions (PRD silent; resolve before leaving backlog):
- The PRD does not define the "variance band": IQR (25th–75th percentile),
  min/max, or a confidence interval.
- Trials log at different wall-clock instants. The PRD does not specify the time
  grid or resampling used to compute a median across trials.
- FR-8 logs time-to-first-crash, but SC5 asks only for coverage and crash plots.
  Is a time-to-first-crash plot required?
- The FR-8 logging side (`fuzzer.py`) has no owner ticket. See AFL-007.

## Acceptance criteria
- [ ] Reads persisted per-trial metrics from a results directory
      (`python harness/plots.py results/`). It runs no fuzzing itself.
- [ ] For each target it writes a coverage-over-time figure (edges vs wall-clock).
- [ ] For each target it writes a unique-crashes-over-time figure (deduped
      crashes vs wall-clock).
- [ ] Each figure shows UNIFORM and FAST together, each with a median line and an
      inter-trial variance band.
- [ ] Figures are written to files under `results/`.

## Technical notes (architect)
- **Inputs:** reuse `aggregate.load_trials()` (AFL-012) and `dedup.bucket_trial()`
  (AFL-013) rather than writing new loading code. Each trial's edge series comes from
  `metrics.csv` (`elapsed_s`, `edges`). Unique crashes form a step function over the
  buckets' `first_elapsed_s`.
- **Interface:** one function, `plot_metric(trials, target: str, metric: str, out:
  Path) -> None`, used for both figures.
- **Time grid** (proposed default — confirm): resample each trial's step function
  onto a 1 s grid from 0 to `seconds` (read from `run.json`), carrying the last value
  forward (`numpy.searchsorted`). Then take percentiles across trials at each grid
  point.
- **Band** (proposed default — confirm): a median line plus an IQR (25th–75th
  percentile) band per arm, matching aggregate.py's median + IQR.
- **Output:** `results/figures/<target>_coverage.png` and
  `results/figures/<target>_unique_crashes.png`, both arms on each figure, with the
  legend showing n trials per arm. Use the matplotlib `Agg` backend (headless).
- A TTFC plot is not required by SC5 and is skipped. Adding one needs a Vision/PRD
  decision.
- The FR-8 logging side has its format defined in the AFL-007 notes. Who implements
  it still needs a req-engineer/crew-lead decision.

## Test approach (tester)
Run on a small synthetic results directory and assert the expected figure files
exist. Visually check for median lines and bands, and confirm both arms appear.

## Log
- 2026-11-07 — created (req-engineer)
