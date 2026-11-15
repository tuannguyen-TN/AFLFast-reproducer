---
id: AFL-012
title: Aggregation — median/IQR, Mann-Whitney U, A12
requirement: FR-9
paper_ref: Klees § statistically sound comparisons (Mann-Whitney U, Vargha-Delaney A12, variance across trials)
module: harness/aggregate.py
depends_on: [AFL-011]
status: done
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
- [x] Reads per-trial metrics from a results directory
      (`python harness/aggregate.py results/`). It runs no fuzzing itself.
- [x] For each (target × schedule × metric) it reports the median and IQR, with
      metrics as in PRD §8: edges covered, unique crashes (deduped), and
      time-to-first-crash per planted bug.
- [x] For each (target × metric) it reports the Mann-Whitney U statistic and its
      **two-sided** p-value for UNIFORM vs FAST (human decision, 2026-11-12). No
      one-sided p-value is computed or reported anywhere.
- [x] For each (target × metric) it reports the Vargha-Delaney effect size
      A12(FAST, UNIFORM), so A12 > 0.5 means FAST's values tend to be larger. Each
      row states which direction is better for its metric (larger for edges and
      coverage area, smaller for TTFC) and which arm A12 favours; the statistic
      itself is never flipped.
- [x] **Coverage scalars (human decision, 2026-11-12).** The primary coverage
      measure is `final_edges`, the edges covered at the end of the trial's budget.
      The secondary, exploratory measure is `edges_auc`, the area under the trial's
      edges-over-time curve on [0, budget] seconds, in edge-seconds (definition in
      the technical notes). Tests: a synthetic `metrics.csv` with rows
      (`elapsed_s`, `edges`) = (0, 10), (100, 20) and a 600 s budget gives
      `final_edges` = 20 and `edges_auc` = 10·100 + 20·500 = 11000.
- [x] **Primary family and Holm-Bonferroni (human decision, 2026-11-12).** The
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
- [x] **Deep-bug ids exist in ground truth (human decision, 2026-11-12).** A test
      asserts that each deep-bug id in the primary family constant (`toy-1`,
      `tlv-2`, `mfp-1`) is a key in `targets/ground_truth.json`. A renamed or
      mistyped id then fails this test loudly, instead of matching no crash and
      sitting in the family censored at p = 1. The test reads the real file, not a
      fixture. It first runs after AFL-009, AFL-010 and AFL-016 have landed their
      ground-truth entries, which AFL-012's dependency chain guarantees (AFL-012
      depends on AFL-011, which depends on all three).
- [x] It writes a UNIFORM vs FAST comparison table holding all of the above, with a
      `family` column (`primary` or `exploratory`) on every row. `summary.md`
      prints the word "exploratory (uncorrected)" next to every exploratory p-value.
- [x] Each row reports the trial count it is based on. A row with fewer than 10
      trials per arm is flagged (SC3).
- [x] **Censored time-to-first-crash (human decision, 2026-11-07).** A planted bug
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
- [x] **Crash-site sentinel counts (human decision, 2026-11-07).** For every trial
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
- 2026-11-15 — started while AFL-011 is still in testing and gaining modes (lead decision, 2026-11-15): the Nov 19 results depend on this module. Built against the results layout the working tree writes (`run.json`, `metrics.csv`, `crash_events.csv`, `campaign.json`); a layout change in AFL-011 may need a follow-up here (developer)
- 2026-11-15 — to review (developer). harness/aggregate.py + tests/test_aggregate.py (20 tests). Exclusion (lead decisions, 2026-11-15): `trial_dirs(results_dir)` skips trials under a `smoke` path component, with `excluded_from_analysis` in campaign.json, or marked aborted (per-trial record "aborted" marker or the campaign "aborted" list, matched on the trailing target/schedule/sN parts); `is_main_trial` additionally requires campaign.json `kind == "main"` (pilot, probe and bare runs excluded). How each AC is met (tests in tests/test_aggregate.py): reads results dir, no fuzzing (`main`, `test_exploratory_row_label_in_markdown`); median/IQR per arm and metric (`test_summary_rows_and_labels`); two-sided asymptotic MWU with continuity, no one-sided p (`test_a12_and_compare`, `test_compare_all_tied`); A12(FAST, UNIFORM) with `better` and `a12_favours` columns (`test_summary_rows_and_labels`); coverage scalars (`test_final_edges_and_auc`, `test_auc_zero_before_first_row`); primary family and Holm (`test_primary_family_constant`, `test_holm_example`, `test_holm_input_order_and_ties`, exploratory labelling in `test_summary_rows_and_labels`); ground-truth ids (`test_deep_bug_ids_in_real_ground_truth`, real file); table with `family` and "exploratory (uncorrected)" in summary.md (`test_exploratory_row_label_in_markdown`); trial counts and low_n (`test_low_n_flag`); censored TTFC (`test_censored_quantiles`, `test_censored_kept_in_test_input_and_all_censored`, `test_summary_rows_and_labels`); sentinel counts and flags (`test_sentinel_counts_and_flag`); exclusions (`test_trial_dirs_and_main_filter`, `test_bare_run_without_campaign_json_excluded`, `test_smoke_and_excluded_trials_skipped`, `test_aborted_trials_dropped`). Open questions for the lead are in the hand-back report. ACs not ticked (reviewer verifies).
- 2026-11-15 — reviewer: BOUNCE → in-progress. Gates: ruff clean on harness/aggregate.py and tests/test_aggregate.py; `mypy src` clean (aggregate.py is outside the gate; its only mypy errors are missing pandas/scipy stubs); tests/test_aggregate.py + tests/test_plots.py 29 passed. Hand-checked: Holm on 0.001, 0.011, 0.012, 0.04, 0.3, 0.6 gives 0.006, 0.055, 0.055, 0.12, 0.6, 0.6 (6×, 5×, 4×0.012 = 0.048 lifted to 0.055 by the running max, 3×, 2×0.3, 1×0.6), only the first < 0.05; `edges_auc` for (0,10),(100,20), budget 600 = 10·100 + 20·500 = 11000, `final_edges` = 20. Met: AC "Reads per-trial metrics" (aggregate.py:303-315, no fuzzer import at runtime beyond dedup's SENTINELS); "median and IQR" (:112-115, :209, :211-213); "two-sided MWU" (:126-127 pinned call, the only `mannwhitneyu` call; no one-sided p anywhere); "A12(FAST, UNIFORM)" (:95-98, :128, `better`/`a12_favours` :205/:210/:216-217, never flipped); "Coverage scalars" (:147-153, :179); "Primary family and Holm" (:32-39 constant, :101-109 step-down with input-order tie-break, :236-240, exploratory rows empty `p_holm`/`significant`); "Deep-bug ids exist in ground truth" (test reads the real file); "comparison table with family column, 'exploratory (uncorrected)' in summary.md" (:257-260, :288); "trial count, low_n" (:211-212, :218). Coupling with AFL-014 holds: `trial_dirs(results_dir) -> list[tuple[Path, dict]]` and `is_main_trial(trial_dir, results_dir) -> bool` unchanged in signature and meaning (but B1 also crashes plots.py, which calls `trial_dirs`). Campaign field names checked against the working-tree run_campaign.py: `kind` (:769), smoke `excluded_from_analysis: True` (:777), per-trial `"aborted": True` in `meta["trials"][str(t.out)]` (:509, :528, :557-559), campaign `"aborted"` list (:533, :561, :797). (reviewer)
  Required changes:
  - **B1 (AC "Reads per-trial metrics"; AFL-011 "Abort stops running trials").** `_aborted` (aggregate.py:62-63) calls `Path(k)` on every `"aborted"` list entry's `trial`, but the runner writes `{"trial": None, ...}` for a runner error (run_campaign.py:561) and for SIGINT/SIGTERM (:797). Reproduced: `TypeError ... not 'NoneType'`. `aggregate.py` and `plots.py` both die on any main campaign that saw Ctrl-C or a runner error. Skip `None` entries (the killed trials are already marked in their per-trial records); add a test with a `{"trial": null}` entry.
  - **B2 (AC "Censored time-to-first-crash": "censored trial ranked ... above every observed time").** The placeholder `budget + 1.0` (aggregate.py:199) is not above every observed TTFC. ADR-0005 allows the last execution to start before the deadline and finish after it, and a crashing execution includes ASan symbolization (what AFL-011's D_max measures, and `timeout_s` is not frozen yet), so a find at e.g. 603 s ranks above the censored trials. Reproduced with fast = [10, 20, 603] + 7 censored vs uniform all censored: U = 45, p = 0.584 with `budget + 1`; U = 35, p = 0.078 with the PRD ranking. Use a value above every observed value in the row (`math.inf` works with the pinned scipy call, checked) and test it with an observed TTFC > budget + 1. Whether a find after the budget counts as found at all is lead question Q10 below.
  - **B3 (technical notes "Primary family": "The family is never resized from the data ... The only exception is a campaign run under AFL-011's `--allow-fewer-targets` override, where a target that was not run has no data").** `build_summary` (aggregate.py:229-231) removes any family target that has no rows, so a target that ran but whose trials were all excluded, or a target-name mismatch, silently gives m = 4 and summary.md then states "(target not run, --allow-fewer-targets)" (:281), which would be false. Read the main campaign.json: remove a member only when `allow_fewer_targets` is non-null and its target is absent from `targets` (run_campaign.py:773-775 records both); any other family target without rows raises. Print the recorded reason in summary.md. Tests: missing target without the override raises; with it, members removed and m stated.
  - **B4 (AC "Crash-site sentinel counts": "For every trial it reports, separately for each of the three AFL-007 sentinels ... the number of rows").** The per-trial counts exist only in the in-memory DataFrame; no output file has them (only nonzero flags reach summary.csv/summary.md). `write_outputs` takes `df` and never uses it (aggregate.py:267). Write a per-trial table (e.g. `results/trials.csv` from `df`: target, schedule, seed, final_edges, edges_auc, unique_crashes, ttfc:*, sentinel:*). It also gives ADR-0003's tripwire (no_stack rows per target and arm) its source.
  - **B5 (tests must exercise the ACs as written).** (a) The AC test "6 of 10 trials censored reports find rate `4/10` and median '> budget'" is not tested: `test_six_of_ten_censored_find_rate` (test_aggregate.py:163-164) checks only the median from `censored_quantiles` and duplicates `test_censored_quantiles`; `find_rate` is checked only at 10/10 and 0/10. Drive a 4-of-10 arm through `build_summary` and assert `find_rate` "4/10", median "> budget" and n = 10. (b) The sentinel flag AC says flagged "in the aggregate output (summary.csv and summary.md)", but `test_sentinel_counts_and_flag` (:167-177) tests only the `_sentinel_flags` helper; assert the flag text in both files via `main`.
  Non-blocking: N1 `compare`'s ValueError for a missing arm (:121) does not name the target/metric; wrap it in `_row`. N2 `budget = g.budget.max()` (:196) silently picks the max if trials of one target have different budgets; assert one budget per target. N3 a main campaign with a non-empty `"aborted"` list still has its completed trials analysed; summary.md should at least say the campaign aborted (lead question Q11).
  Developer questions: Q1 (i) field names match the working tree (lines above) except the `None` trial entries (B1). Q2 (ii) safe default: a bare CLI run has no run kind, and AFL-011 records the kind only in campaign.json. Q3 (ii) safe default, descriptive only (p, A12 and Holm unchanged): with exactly half censored the interpolated median involves a censored trial and is not determinable; "> budget" overstates slightly (it is only known to exceed (x(n/2) + budget)/2), so say "not determinable / not reached" in the summary.md legend; Kaplan-Meier's x(n/2) is the alternative if the lead prefers. Q4 (i) ADR-0003 Consequences: "unique crashes = `len(buckets)`" and "Sentinel buckets inflate the unique-crash count ... AFL-012 flags nonzero sentinel counts". Q5 (i) technical notes "mini format parser (AFL-016 binary name)"; the binary is `mini_format` in main.yaml, targets/Makefile and ground_truth.json (`mfp-1`, `mfp-2`). Q6 (i), against the developer's choice: see B3. Q7 (ii) safe default, a comparison with an empty arm is undefined; improve the message (N1). Q8 (ii) safe default, the AC asks for the flag in both files and naming target/schedule/seed; repeating per row of the target is acceptable. Q9 (i)/(ii) technical notes "`None` if the bug was never found"; NaN is pandas' form of it and `_row` maps it back (:197). New for the lead: Q10 (iii) does a planted-bug crash recorded after the budget (the ADR-0005 overrun execution) count as found, or as censored per the AC's "not found within a trial's budget"? Recommendation: censored, which matches the AC wording and the [0, budget] window of `edges_auc`; B2's fix is needed either way. Q11 (iii) is a main campaign that aborted part-way analysed from its completed trials, or not at all? Recommendation: not analysed as the main result (an aborted campaign is unbalanced and was stopped for a reason); at minimum aggregate refuses or warns loudly.
- 2026-11-15 — to review again after first bounce (developer). harness/aggregate.py + tests/test_aggregate.py (31 tests). B1 `_aborted` skips `trial: None` entries (test_campaign_level_abort_with_null_trial). B2 censored placeholder is `CENSORED = math.inf` (test_censored_ranks_above_observed_beyond_budget: U = 35, p = 0.078). B3 `build_summary(df, campaign)` removes a family member only if campaign.json has non-empty `allow_fewer_targets` and the target is absent from its `targets`, else raises; summary.md prints the recorded reason (test_missing_target_without_override_raises, test_removed_members_and_reason_in_summary). B4 `write_outputs` writes `trials.csv` (one row per trial: target, schedule, seed, budget, final_edges, edges_auc, unique_crashes, ttfc:*, sentinel:* incl. no_stack). B5 (a) test_six_of_ten_censored_find_rate drives 4-of-10 through build_summary: "4/10", "> budget", n = 10; (b) test_sentinel_counts_and_flag asserts the flag text in summary.csv and summary.md via `main`, and trials.csv counts. N1 missing-arm error names target and metric (test_missing_arm_error_names_target_and_metric); N2 differing budgets per target raise (test_differing_budgets_raise). Defaults pending lead ruling: Q10 a first crash after the budget counts as NOT found (censored), test_late_find_after_budget_is_censored; Q11 `main_campaign()` makes aggregate refuse a main campaign with any abort, error names the campaign dir, `main` returns 1 (test_aborted_trials_dropped, test_campaign_level_abort_with_null_trial; covers N3); Q3 exactly half censored on an even n gives the median "not determinable (>= half not reached)", explained in the summary.md legend, p/A12/Holm unchanged (test_half_censored_median_not_determinable). plots.py untouched; tests/test_plots.py passes. (developer)
- 2026-11-15 — reviewer (second review): APPROVE → testing. Gates: ruff clean on harness/aggregate.py and tests/test_aggregate.py; `mypy src` clean; tests/test_aggregate.py + tests/test_plots.py 37 passed (test_aggregate.py has 28 tests, not 31). Each fix was checked by mutating a scratch copy; every mutant below was killed. B1 (aggregate.py:63 skips `trial: None`): killed by test_campaign_level_abort_with_null_trial. B2 (`CENSORED = math.inf`, :215): mutant `601.0` killed by test_censored_ranks_above_observed_beyond_budget (U = 35, p = 0.078). B3 (:271-278): three mutants (no check; override ignores `targets`; override always on) killed by test_missing_target_without_override_raises; reason dropped from summary.md killed by test_removed_members_and_reason_in_summary. Key names match run_campaign.py: `allow_fewer_targets` is None or a non-empty reason (:694, :775) and `targets` holds basenames (:256, :773). B4 (trials.csv, :319): killed by test_sentinel_counts_and_flag. B5a (find rate miscounted, censored trials dropped, median clamped to a number): killed by test_six_of_ten_censored_find_rate and others. B5b (flags missing from summary.md, or from summary.csv): killed by test_sentinel_counts_and_flag. N1: killed by test_missing_arm_error_names_target_and_metric. N2: killed by test_differing_budgets_raise. Defaults pending the lead: Q10 (`v > budget` → censored, :234) killed by test_late_find_after_budget_is_censored; Q11 refusal killed by test_aborted_trials_dropped; Q3 branch killed by test_half_censored_median_not_determinable. Probed by hand, outside the tests: the Q3 cell reads "not determinable (>= half not reached)" in both summary.csv and summary.md, and the legend explains it; Q11 refuses a campaign with only per-trial `aborted` markers (rc 1), with only a SIGINT `{"trial": null}` entry (rc 1), and with several main campaigns (rc 1, every dir named); a three-target run_campaign-shaped campaign with `allow_fewer_targets: null` gives m = 6 of 6. Full AC pass: every AC was re-verified against the current file (reads results dir, median/IQR, two-sided pinned MWU and the only `mannwhitneyu` call, A12(FAST, UNIFORM) never flipped, with `better`/`a12_favours`; coverage scalars; family constant and Holm; ground-truth ids from the real file; `family` column and "exploratory (uncorrected)"; n and low_n; censored TTFC; sentinel counts per trial in trials.csv, with flags in both summary files). AFL-014 coupling: the `trial_dirs` and `is_main_trial` signatures and meaning are unchanged, and tests/test_plots.py passes. However, plots.py never calls `main_campaign`, so on an aborted main campaign it still plots the completed trials and returns 0, while aggregate refuses with rc 1 (probed). That is for the lead's Q11 ruling and AFL-014. Non-blocking: (F1, for the Q10 ruling) the window is not consistent across metrics. A crash after the budget is censored for TTFC, but the same trial's `unique_crashes` counts its bucket (:204). `final_edges` is the last metrics row (:203), and that row is always at or past the deadline (fuzzer.py:208), so it includes coverage from the ADR-0005 overrun execution. trials.csv also shows the raw TTFC > budget. If the lead rules "censored", the follow-up is to compute `final_edges` and `unique_crashes` on [0, budget]; if the lead rules "found", it is to drop `or v > budget`. (F2) The mutants survive test gaps where the code is correct by inspection and by probe: `low_n` computed with max instead of min (both arms of test_low_n_flag have n = 3); Q11 refusal on per-trial markers only, and the several-mains refusal; the Q3 text in summary.md and its legend. (F3) The q1 and q3 cells show "> budget" when their interpolation straddles an observed value and a censored one. The quantile is then only known to exceed a weighted point below the budget, the same overstatement Q3 fixed for the median; descriptive cells only, p, A12 and Holm are unaffected. (F4) The comment at test_aggregate.py:126 says "m = 4"; it is m = 2 (4 removed). (reviewer)
- 2026-11-15 — developer: applied review Findings 2-4 (harness/aggregate.py, tests/test_aggregate.py; test_aggregate.py now 33 tests, +test_plots 9 = 42 passed). F3: a quartile whose interpolation falls between an observed and a censored time is "not determinable (interpolates a not-reached trial)" (`STRADDLE`, aggregate.py:42,164-166; the median keeps HALF_CENSORED); wholly-censored quantiles stay "> budget"; legend updated; p, A12, Holm, Q10, Q11, B1-B5, trial_dirs/is_main_trial untouched. F2 tests: test_low_n_uses_min_of_arm_sizes, test_refusal_from_per_trial_aborted_marker_only, test_several_main_campaigns_refused_naming_each, test_half_censored_wording_in_summary_md, test_quartile_straddling_censored_not_determinable; each killed by a scratch mutant. F4: comment at test_aggregate.py:126 fixed (4 removed, m = 2). (developer)
- 2026-11-15 tester: FAIL (every AC passes; one exclusion hole). Gates: ruff clean (harness/aggregate.py, tests/test_aggregate.py); `mypy src` clean; tests/test_aggregate.py + tests/test_plots.py 42 passed. Per AC: reads results dir, no fuzzing PASS (only fuzzer import is dedup's SENTINELS; probe of a run_campaign-shaped tree with main + smoke + pilot + probe gives rc 0, 60 main trials only); median/IQR per (target x schedule x metric) PASS (summary.csv/md, IQR cells); two-sided MWU PASS (the only `mannwhitneyu` call, pinned; no greater/less anywhere in harness/; mutants alternative=greater/less, p/2, no continuity, method=exact killed); A12(FAST, UNIFORM) never flipped, `better`/`a12_favours` PASS (mutants swapped args, a<b, ties 0/1, favours flipped, TTFC better=larger, arms swapped killed); coverage scalars PASS (20 and 11000, test_final_edges_and_auc); primary family + Holm PASS (constant test; 0.006/0.055/0.055/0.12/0.6/0.6; mutants no running max, (k+1)x, m x, descending sort, sorted-order output, Holm over all rows killed); deep-bug ids in real ground_truth.json PASS; `family` column + "exploratory (uncorrected)" PASS (label-dropped and exploratory p_holm-filled mutants killed); n per row + low_n PASS (min/max mutant killed); censored TTFC PASS (4/10 and "> budget", n kept at 10, all-censored p = 1/A12 = 0.5 stays primary; mutants CENSORED = 601/600/0/-inf, censored dropped, late find counted, median clamped, find rate = n, STRADDLE removed killed); sentinel counts PASS (trials.csv per trial, flags in summary.csv and summary.md, test_sentinel_counts_and_flag). Exclusions: smoke path, `excluded_from_analysis`, pilot/probe/bare (kind != main), per-trial `aborted`, campaign `aborted` list incl. `trial: null` (SIGINT probe rc 1), several mains, `allow_fewer_targets` null with 3 targets (m = 6 of 6) and with a reason and 2 targets (m = 4 of 6) all PASS, each smoke/abort branch killed by a mutant. FAIL: a main campaign aborted without a record (runner SIGKILLed, machine died, or aggregate run while the campaign is still running) reaches the analysis: campaign.json has no `finished_at` and no `aborted` entry, run.json exists from trial start, so truncated trials are analysed. Probe: 10/10 per arm, 3 uniform trials per target stopped at 120 s of a 600 s budget gives rc 0, m = 6 of 6, no LOW N flag; the truncated trial's `final_edges` is its 120 s value and its `edges_auc` holds that value to 600 s (12360). Fix suggestion: `main_campaign` refuses a main campaign.json without `finished_at`, and `load_trials` refuses a main trial whose last metrics row has `elapsed_s` < budget (fuzzer.py:208 writes a final row at or past the deadline); one test each. Surviving mutants, test gaps with code correct by inspection: `significant` from raw p instead of p_holm (no test reads the `significant` column of a family where Holm changes the verdict); method="auto" (identical p at n = 10; differs only for untied n <= 8); low_n at n < 9 (no n = 9 test); edges_auc without clipping at the budget (no test has a row past the budget, which every real final row is); main_campaign smoke-path check removed (equivalent: runner smoke campaigns have kind smoke). This would be the ticket's second bounce, so it goes to the lead. (tester)
- 2026-11-15 — closed by crew-lead to done/ (lead decision, 2026-11-15). All 11 ACs passed the tester and are ticked. The tester's FAIL concerned a gap (no `finished_at` / truncated trials reaching the analysis, plus test gaps), not the ACs or a defect in AFL-012's stated behaviour; it is not a second bounce. Follow-up AFL-033 (tickets/backlog/AFL-033-*.md, created by the req-engineer) covers: the two guards (main campaign without `finished_at`; last metrics row before the budget); the two missing tests (`significant` from `p_holm`; `edges_auc` clipped at the budget); the Q10 cutoff; the Q3 lower bound; the Q4 exclusion of sentinels from unique crashes; the same guards and rules in `plots.py`. Lead rulings: Q3 "not determinable" accepted, with a lower bound to be reported (AFL-033); Q4 unique crashes exclude the sentinel buckets (AFL-033; ADR-0003 updated); Q10 "not found" everywhere, with a PRD §8 sentence (AFL-033); Q11 aggregate's refusal stands, and `plots.py` gets it via AFL-014. No code changed at close. (lead decision, 2026-11-15)
