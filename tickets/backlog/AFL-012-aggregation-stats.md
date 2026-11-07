---
id: AFL-012
title: Aggregation — median/IQR, Mann-Whitney U, A12
requirement: FR-9
paper_ref: Klees § statistically sound comparisons (Mann-Whitney U, Vargha-Delaney A12, variance across trials)
module: harness/aggregate.py
depends_on: [AFL-011]
status: backlog
owner: developer
---

## Goal
Turn the persisted per-trial metrics into the UNIFORM vs FAST comparison that
Klees requires (FR-9, SC4, PRD §8). For each metric this means median and IQR,
Mann-Whitney U (U and p) and A12 effect size. All of it runs offline from saved
results.

Open questions (PRD silent; resolve before leaving backlog):
- Time-to-first-crash when a trial never crashes is censored data. The PRD does
  not say how to handle it, e.g. set it to the budget value or exclude the trial.
- H1 is directional (FAST ≥ UNIFORM), but the PRD does not say whether the
  Mann-Whitney U test is one-sided or two-sided.
- With several metrics × targets there are multiple comparisons. The PRD does not
  say whether to correct for this.
- "Edges covered over time" is a time series. Which scalar is tested: final
  coverage at the end of the budget, or something else?

## Acceptance criteria
- [ ] Reads per-trial metrics from a results directory
      (`python harness/aggregate.py results/`). It runs no fuzzing itself.
- [ ] For each (target × schedule × metric) it reports the median and IQR, with
      metrics as in PRD §8: edges covered, unique crashes (deduped), and
      time-to-first-crash per planted bug.
- [ ] For each (target × metric) it reports the Mann-Whitney U statistic and its
      p-value for UNIFORM vs FAST.
- [ ] For each (target × metric) it reports the Vargha-Delaney A12 effect size.
- [ ] It marks results significant at α = 0.05.
- [ ] It writes a UNIFORM vs FAST comparison table holding all of the above.
- [ ] Each row reports the trial count it is based on. A row with fewer than 10
      trials per arm is flagged (SC3).

## Technical notes (architect)
- **Loading:** `load_trials(results_dir: Path) -> pandas.DataFrame` globs
  `**/run.json` and takes target, schedule and seed from that file, not from
  directory names. It then reads `metrics.csv` and calls `dedup.bucket_trial()`
  (AFL-013). One row per trial: target, schedule, seed, final_edges, unique_crashes,
  and TTFC per bug_id (`None` if the bug was never found). plots.py (AFL-014) reuses
  this loader.
- **Stats** (pure, unit-testable):
  ```python
  def a12(x: Sequence[float], y: Sequence[float]) -> float: ...  # P(X>Y) + 0.5*P(X=Y)
  def compare(fast: Sequence[float], uniform: Sequence[float], alternative: str) -> dict: ...
      # U and p via scipy.stats.mannwhitneyu, plus A12, medians, IQRs
  ```
  A12 is hand-written (a few lines); U and p come from scipy, which is already pinned.
- **A12 orientation** (proposed default — confirm): always A12(FAST, UNIFORM), so
  > 0.5 means FAST's values are larger. For TTFC smaller is better, so the table states
  the better direction per metric rather than flipping the statistic.
- **Output:** `results/summary.csv` and `results/summary.md`, one row per (target,
  metric): n_uniform, n_fast, median + IQR per arm, U, p, A12, `significant`
  (p < 0.05), and a `low_n` flag for < 10 trials per arm.
- **Needs Vision/PRD decision.** Left open; each one is a single parameter or function,
  so the decision costs no redesign:
  - one-sided vs two-sided Mann-Whitney U → the `alternative` parameter;
  - censored TTFC (no crash within the budget) → the trial keeps `None`, and one
    function applies the policy (impute the budget, exclude, or report the find rate);
  - multiple-comparison correction → raw p is always reported; a corrected column is
    added if a correction is decided;
  - which scalar represents coverage → `final_edges` is loaded (the usual choice);
    confirm it or name another.
- Reads files only. It never runs targets and needs nothing from `fuzzer` at runtime.

## Test approach (tester)
Unit tests on synthetic samples with known U, p and A12 (e.g. identical samples
give A12 = 0.5, fully separated samples give A12 = 1.0). Validity check: no
single-run comparisons, and the trial count is shown.

## Log
- 2026-11-07 — created (req-engineer)
