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
- ~~Time-to-first-crash when a trial never crashes is censored data. The PRD does
  not say how to handle it, e.g. set it to the budget value or exclude the trial.~~
  **Resolved (human, 2026-11-07):** right-censored at the budget; see the
  "Censored time-to-first-crash" AC.
- ~~H1 is directional (FAST ≥ UNIFORM), but the PRD does not say whether the
  Mann-Whitney U test is one-sided or two-sided.~~
  **Resolved (human, 2026-11-12):** two-sided, α = 0.05, with A12 giving the
  direction and the effect size (PRD §8 Analysis, H1).
- ~~With several metrics × targets there are multiple comparisons. The PRD does not
  say whether to correct for this.~~
  **Resolved (human, 2026-11-12):** Holm-Bonferroni across a pre-specified primary
  family (per target final edges; per deep bug TTFC); every other comparison is
  exploratory, uncorrected and labelled as such. See the "Primary family and
  Holm-Bonferroni" AC.
- ~~"Edges covered over time" is a time series. Which scalar is tested: final
  coverage at the end of the budget, or something else?~~
  **Resolved (human, 2026-11-12):** final edges at the end of the budget is the
  primary measure; the area under the coverage-over-time curve is a secondary,
  exploratory measure. See the "Coverage scalars" AC.

## Acceptance criteria
- [ ] Reads per-trial metrics from a results directory
      (`python harness/aggregate.py results/`). It runs no fuzzing itself.
- [ ] For each (target × schedule × metric) it reports the median and IQR, with
      metrics as in PRD §8: edges covered, unique crashes (deduped), and
      time-to-first-crash per planted bug.
- [ ] For each (target × metric) it reports the Mann-Whitney U statistic and its
      **two-sided** p-value for UNIFORM vs FAST (human decision, 2026-11-12). No
      one-sided p-value is computed or reported anywhere.
- [ ] For each (target × metric) it reports the Vargha-Delaney effect size
      A12(FAST, UNIFORM), so A12 > 0.5 means FAST's values tend to be larger. Each
      row states which direction is better for its metric (larger for edges and
      coverage area, smaller for TTFC) and which arm A12 favours; the statistic
      itself is never flipped.
- [ ] **Coverage scalars (human decision, 2026-11-12).** The primary coverage
      measure is `final_edges`, the edges covered at the end of the trial's budget.
      The secondary, exploratory measure is `edges_auc`, the area under the trial's
      edges-over-time curve on [0, budget] seconds, in edge-seconds (definition in
      the technical notes). Tests: a synthetic `metrics.csv` with rows
      (`elapsed_s`, `edges`) = (0, 10), (100, 20) and a 600 s budget gives
      `final_edges` = 20 and `edges_auc` = 10·100 + 20·500 = 11000.
- [ ] **Primary family and Holm-Bonferroni (human decision, 2026-11-12).** The
      primary family is exactly the six comparisons listed in the technical notes:
      `final_edges` for each of toy_parser, tlv_parser and the mini format parser,
      and TTFC for each deep bug, `toy-1`, `tlv-2` and `mfp-1`. It is a constant in
      `aggregate.py`, not derived from the data. Holm-Bonferroni is applied across
      that family only, giving `p_holm` per member. A primary row is
      `significant` iff `p_holm < 0.05`. Every other row is labelled `exploratory`,
      reports its raw p only, has an empty `p_holm` and an empty `significant`, and
      is never corrected. Tests: (a) the family constant equals those six members;
      (b) raw p-values 0.001, 0.011, 0.012, 0.04, 0.3, 0.6 give `p_holm` 0.006,
      0.055, 0.055, 0.12, 0.6, 0.6, so only the first is significant (the third,
      at 4 × 0.012 = 0.048, is not, because Holm stops at the second); (c) an
      exploratory row with raw p = 0.01 has `significant` empty and the label
      `exploratory`.
- [ ] **Deep-bug ids exist in ground truth (human decision, 2026-11-12).** A test
      asserts that each deep-bug id in the primary family constant (`toy-1`,
      `tlv-2`, `mfp-1`) is a key in `targets/ground_truth.json`. A renamed or
      mistyped id then fails this test loudly, instead of matching no crash and
      sitting in the family censored at p = 1. The test reads the real file, not a
      fixture. It first runs after AFL-009, AFL-010 and AFL-016 have landed their
      ground-truth entries, which AFL-012's dependency chain guarantees (AFL-012
      depends on AFL-011, which depends on all three).
- [ ] It writes a UNIFORM vs FAST comparison table holding all of the above, with a
      `family` column (`primary` or `exploratory`) on every row. `summary.md`
      prints the word "exploratory (uncorrected)" next to every exploratory p-value.
- [ ] Each row reports the trial count it is based on. A row with fewer than 10
      trials per arm is flagged (SC3).
- [ ] **Censored time-to-first-crash (human decision, 2026-11-07).** A planted bug
      not found within a trial's budget gives a TTFC that is **right-censored at
      the budget**. A censored trial is never dropped (dropping biases the result
      toward the arm that finds the bug less often) and is never reported as an
      observed time equal to the budget (clamping). Per (target × bug × arm) the
      table reports the find rate `k/n` and the median TTFC; when > 50 % of that
      arm's trials are censored, the median is reported as "> budget" (not
      reached), not as a number. The TTFC significance test is censoring-aware:
      the two-sided Mann-Whitney U test with every censored trial ranked as tied
      with the other censored trials and above every observed time (PRD §8
      Analysis; human decision, 2026-11-12; details in the technical notes).
      Tests: a synthetic arm with 6 of 10 trials censored reports find rate `4/10`
      and median "> budget"; an arm with censored trials keeps n = 10 in the test
      input; when every trial in both arms is censored, the row reports p = 1 and
      A12 = 0.5, and if the bug is in the primary family it stays in the family.
- [ ] **Crash-site sentinel counts (human decision, 2026-11-07).** For every trial
      it reports, separately for each of the three AFL-007 sentinels
      (`"no_stack"`, `"unsymbolized"`, `"no_target_frame"`), the number of
      `crash_events.csv` rows whose `crash_site` is that sentinel. Any nonzero
      count in a main-campaign trial is flagged in the aggregate output
      (`summary.csv` and `summary.md`), naming the trial (target, schedule, seed)
      and the sentinel. Tests: a synthetic main-campaign trial with one
      `"unsymbolized"` row is flagged with count 1; one with a `"no_stack"` row is
      flagged with count 1 for `"no_stack"`; a trial with none has all three
      counts 0 and no flag.

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
  def compare(fast: Sequence[float], uniform: Sequence[float]) -> dict: ...
      # U and two-sided p via scipy.stats.mannwhitneyu, plus A12, medians, IQRs
  def holm(pvals: Sequence[float]) -> list[float]: ...  # adjusted p, input order
  ```
  A12 and Holm are hand-written (a few lines each); U and p come from scipy, which is
  already pinned. The `alternative` parameter is gone: the test is always two-sided
  (decided, PRD §8).
- **Mann-Whitney U call (decided, PRD §8):** `scipy.stats.mannwhitneyu(fast, uniform,
  alternative="two-sided", method="asymptotic", use_continuity=True)` for every row,
  primary or exploratory. The method is pinned so the p-value does not change with
  scipy's `"auto"` rule; the asymptotic method applies the tie correction that
  censored TTFC values need. If all pooled values of a row are identical (e.g. every
  trial in both arms censored), the variance is zero and scipy's p is undefined, so
  `compare` returns p = 1.0 and A12 = 0.5 without calling scipy.
- **A12 orientation (fixed by PRD §8, 2026-11-12):** always A12(FAST, UNIFORM), so
  > 0.5 means FAST's values are larger. For TTFC smaller is better, so the table states
  the better direction per metric rather than flipping the statistic. Ties count 0.5
  (`P(X>Y) + 0.5·P(X=Y)`), so two censored TTFC values count as a tie.
- **Primary family (decided, PRD §8), m = 6,** in this fixed order:
  1. `final_edges`, toy_parser
  2. `final_edges`, tlv_parser
  3. `final_edges`, mini format parser (AFL-016 binary name)
  4. TTFC `toy-1` (toy_parser, deep, AFL-009)
  5. TTFC `tlv-2` (tlv_parser, deep, AFL-010)
  6. TTFC `mfp-1` (mini format parser, deep, AFL-016)

  The deep bug ids come from the target tickets, because `targets/ground_truth.json`
  records no depth field. A retune (AFL-011) changes a target but keeps its bug ids,
  so the family does not change. The family is never resized from the data: a
  member whose rows are all censored stays in with p = 1. The only exception is a
  campaign run under AFL-011's `--allow-fewer-targets` override, where a target that
  was not run has no data; its two members are then removed, m shrinks accordingly,
  and `summary.md` states the removed members and the m actually used.
- **Holm's step-down (decided, PRD §8):** sort the m raw p-values ascending,
  p(1) ≤ … ≤ p(m), breaking ties by the family order above so the result is
  deterministic. Adjusted p(k) = min(1, max over j ≤ k of (m − j + 1)·p(j)). Report
  adjusted values in family order. A member is significant iff its adjusted p < 0.05,
  which is equivalent to Holm stopping at the first k with p(k) ≥ 0.05 / (m − k + 1).
  Tied raw p-values get equal adjusted values, whatever their order.
- **Coverage area (exploratory):** `metrics.csv` (AFL-007) writes a row whenever edges
  change, so edges(t) is a step function: it holds each row's `edges` from that row's
  `elapsed_s` until the next row's, and the last row's value holds until the budget
  (`seconds_per_trial` from `run.json`). edges(t) is 0 before the first row.
  `edges_auc` = ∫₀^budget edges(t) dt, in edge-seconds.
- **Output:** `results/summary.csv` and `results/summary.md`, one row per (target,
  metric): n_uniform, n_fast, median + IQR per arm, U, p (raw, two-sided), A12,
  `family` (`primary` / `exploratory`), `p_holm` and `significant` (`p_holm` < 0.05;
  both empty on exploratory rows), and a `low_n` flag for < 10 trials per arm.
- **Censored TTFC (decided, see AC and PRD §8):** the loader keeps `None` for a bug
  not found; one function maps it to a censored value. With a common fixed censoring
  time (every trial has the same budget), Mann-Whitney U with censored values ranked
  as ties above all observed values is equivalent to Gehan's generalized Wilcoxon
  test, so `scipy.stats.mannwhitneyu` on censored values set to one common number
  greater than the budget (e.g. `budget + 1.0`) works unchanged. Every censored value
  in a row uses the same number, so the censored trials tie with each other. The
  log-rank alternative is not used.
- Reads files only. It never runs targets and needs nothing from `fuzzer` at runtime.

## Test approach (tester)
Unit tests on synthetic samples with known U, p and A12 (e.g. identical samples
give A12 = 0.5, fully separated samples give A12 = 1.0). Validity check: no
single-run comparisons, and the trial count is shown.

## Log
- 2026-11-07 — created (req-engineer)
- 2026-11-07 — per human decision: TTFC for an unfound bug is right-censored at
  the budget (never dropped, never clamped); added AC for find rate k/n, "> budget"
  median, censoring-aware test; architect note names Gehan / log-rank candidates.
  Removed the censoring item from open questions (req-engineer)
- 2026-11-07 — review fix: added AC for per-trial counts of the "unsymbolized" and "no_target_frame" crash-site sentinels, with any nonzero main-campaign count flagged in the aggregate output (human decision) (req-engineer)
- 2026-11-07 — review fix: sentinel-count AC covers all three AFL-007 sentinels (`"no_stack"` added), each counted and flagged, test added (human decision) (req-engineer)
- 2026-11-12 — statistics pre-registered (human decision), PRD §5 SC4, §6 FR-9 and §8 Analysis / H1 changed to match. The three open questions are resolved: the Mann-Whitney U test is two-sided at α = 0.05, with A12(FAST, UNIFORM) giving the direction and effect size; Holm-Bonferroni runs across a fixed primary family of m = 6 (final edges per target; TTFC per deep bug `toy-1`, `tlv-2`, `mfp-1`), and every other row is exploratory, uncorrected and labelled; `final_edges` is the primary coverage measure and `edges_auc` is secondary and exploratory. The censored-TTFC test is now named (two-sided Mann-Whitney U with censored trials tied above all observed times, i.e. Gehan; log-rank dropped). Added ACs for the coverage scalars and for the primary family with Holm, plus technical notes on the pinned scipy call, the all-tied case, the family order, Holm's step-down and the coverage-area definition (req-engineer)
- 2026-11-12 — added AC: a test asserts each primary-family deep-bug id (`toy-1`, `tlv-2`, `mfp-1`) is a key in `targets/ground_truth.json`, so a renamed or mistyped id fails loudly rather than sitting censored at p = 1; it first runs once AFL-009, AFL-010 and AFL-016 have landed their entries, guaranteed by the dependency chain via AFL-011 (human decision) (req-engineer)
