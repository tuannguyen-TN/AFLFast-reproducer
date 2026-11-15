---
id: AFL-033
title: Aggregate and plots — endpoint cutoff at the budget, truncated-campaign guards, sentinel-free unique crashes
requirement: FR-9, PRD §8 (endpoints; censored TTFC; crash dedup), FR-8
paper_ref: Klees (statistically sound comparisons, censored time-to-bug, honest crash counting)
module: harness/aggregate.py, harness/plots.py, tests/test_aggregate.py, tests/test_plots.py
depends_on: [AFL-012, AFL-014]
status: backlog
owner: developer
---

## Goal
Make the analysis match the lead's 2026-11-15 rulings, and close the tester's
AFL-012 exclusion hole:
- the analysis refuses an unfinished or truncated main campaign;
- every endpoint is cut at the budget (Q10);
- a median or quartile that cannot be determined reports its lower bound (Q3);
- unique crashes exclude the sentinel buckets (Q4).

aggregate and plots must agree on all of these.

Timing: this ticket is analysis-only and must land before the analysis runs on
2026-11-19. It is **not** a pre-freeze item and is not in the AFL-011 freeze set.
None of its code runs during the campaign: it reads only the persisted results.

## Acceptance criteria
- [ ] **1. Guards against unfinished or truncated main campaigns.** The tester's
      AFL-012 probe failed on these (3 uniform trials per target cut at 120 s of
      a 600 s budget gave rc 0 and m = 6/6). `aggregate.py main` returns 1, prints
      an error naming the offending directory, and writes no `summary.csv`,
      `summary.md` or `trials.csv`, when either of these holds:
      - (a) The main campaign's `campaign.json` has no `finished_at` key.
        `finished_at` lives in `campaign.json`, written by run_campaign.py at the
        end of the run; `run.json` has no such field. This covers a runner
        killed without a record, a dead machine, and aggregate run while the
        campaign is still going.
      - (b) A main-campaign trial's last `metrics.csv` row has `elapsed_s` below
        that trial's budget (`run.json` `config.seconds`). A time-stopped trial
        always writes a final row at or past the deadline (fuzzer.py:208).

      Tests:
      - a main campaign.json without `finished_at` gives rc 1;
      - the tester's probe gives rc 1 and the error names a truncated trial.
        The probe: 10 trials per arm per target, 3 uniform trials per target
        whose last row is at 120 s of a 600 s budget, `finished_at` present;
      - the same tree with every trial ending at or past 600 s gives rc 0.
- [ ] **2. Missing tests for existing behaviour.**
      - (a) `significant` is decided from `p_holm`, not the raw `p`. A test
        drives a primary family through `build_summary` in which one member has
        raw p < 0.05 and `p_holm` ≥ 0.05. Example: raw 0.001, 0.011, 0.012,
        0.04, 0.3, 0.6 gives `p_holm` 0.006, 0.055, 0.055, 0.12, 0.6, 0.6. The
        test asserts that member's `significant` column is False, and that the
        member with p_holm 0.006 is True. It must fail if `significant` is
        computed from raw p.
      - (b) `edges_auc` is clipped at the budget. With metrics rows (0, 10),
        (100, 20), (605, 25) and a 600 s budget, `edges_auc` = 10·100 + 20·500
        = 11000. The row past the budget adds nothing.
- [ ] **3. Q10 endpoint cutoff, in every endpoint.** Source: PRD §8 Dependent
      variables, "Endpoints are evaluated at the end of the budget; an execution
      that finishes after the deadline (the at-most-one-execution overrun,
      ADR-0005 §2) contributes to no endpoint." (lead decision, 2026-11-15).
      Budget = the trial's `run.json` `config.seconds`. The cutoff is applied in
      `load_trials`, so `trials.csv` and `summary.*` show the same cut values.
      - (a) `final_edges` is the `edges` value of the last `metrics.csv` row with
        `elapsed_s` ≤ budget, not the last row. Test: rows (0, 10), (100, 20),
        (605, 25), budget 600, gives `final_edges` = 20.
      - (b) `unique_crashes` counts only buckets whose `first_elapsed_s` ≤
        budget. Test: one real-site bucket first seen at 603 s, budget 600, is
        not counted.
      - (c) `ttfc:<bug>` counts only crash events with `elapsed_s` ≤ budget. A
        bug whose first event comes after the deadline is "not found"
        (censored): `None`/NaN in `trials.csv`, not counted in `find_rate`,
        ranked as censored in the test. Test: a planted-bug event at 603 s,
        budget 600, gives an empty `ttfc` in `trials.csv`, and that trial is
        not counted in its arm's find rate. The existing `test_late_find_after_budget_is_censored` may
        be extended.
      - (d) The per-trial sentinel counts (`sentinel:<name>`) are a validity flag,
        not an endpoint. They keep counting every `crash_events.csv` row,
        including rows after the deadline, as they do now (lead decision,
        2026-11-15: a data-quality monitor sees every row; the end-of-budget
        cutoff applies only to endpoints).
- [ ] **4. Q3 lower bound for medians and quartiles that cannot be determined.**
      Notation: n = the arm's trial count, k = its number of observed (uncensored)
      times, x(1) ≤ … ≤ x(k) = its observed times in ascending order, and
      h = (n − 1)·q for quantile q (the linear interpolation used now).
      - (a) Median at exactly 50 % censored (n even, k = n/2): the cell is no
        longer a bare label. It starts with `>= t` and keeps the words "not
        determinable". t = x(n/2), the (n/2)-th order statistic of the arm, i.e.
        its largest observed time. The interpolated median lies between x(n/2)
        and a censored value, so x(n/2) is a valid lower bound. The current
        `HALF_CENSORED` label ("not determinable (>= half not reached)",
        aggregate.py:41) is kept as the text after the bound.

        Test: n = 10, observed 10, 20, 30, 40, 50 plus 5 censored, budget 600.
        The median cell starts with `>= 50` and contains "not determinable".
        q1 = 32.5 (numeric). q3 = "> budget".
      - (b) Quartiles in the same way. A quartile whose interpolation falls
        between an observed and a censored time (⌊h⌋ < k ≤ ⌈h⌉ and ⌊h⌋ ≠ ⌈h⌉,
        the current `STRADDLE` case, aggregate.py:42 and :164) starts with
        `>= t`, where t = x(⌊h⌋ + 1) = x(k), the arm's largest observed time. It
        keeps the `STRADDLE` text after the bound.

        Test: n = 10, observed 10, 20, 30 plus 7 censored. q1 (h = 2.25) starts
        with `>= 30` and contains "not determinable". The median is
        "> budget".
      - (c) "> budget" stays unchanged when more than 50 % of the arm is
        censored (median), and whenever the quantile's interpolation lies wholly
        in the censored tail (⌈h⌉ ≥ k and the case is not (b)).
      - (d) The bound is formatted as `_fmt` formats numbers. The `summary.md`
        legend says the number is a lower bound, not an estimate. p, U, A12 and
        Holm are unchanged; this is descriptive only.
- [ ] **5. Q4 unique crashes exclude the sentinels.** (lead decision,
      2026-11-15; ADR-0003 "Sentinels" and Consequences: "Unique crashes = the
      number of buckets whose key is not a sentinel and whose `first_elapsed_s` ≤
      the budget".)
      - `unique_crashes` counts only buckets whose key is not one of `no_stack`,
        `unsymbolized` or `no_target_frame`, cut as in AC 3(b).
      - The three `sentinel:<name>` per-trial counts in `trials.csv`, and the
        sentinel flags in `summary.csv` and `summary.md`, stay reported
        separately, unchanged.
      - The `load_trials` docstring no longer says "all dedup buckets, sentinels
        included". It states the sentinel exclusion and the budget cutoff.

      Test: a trial with one real-site bucket and one `no_stack` bucket has
      `unique_crashes` = 1 and `sentinel:no_stack` = 1.
- [ ] **6. plots.py applies AC 1's guards through the shared aggregate code.**
      `plots.py main` calls the same aggregate function(s) that enforce AC 1
      (a) and (b). It does not reimplement them: `harness/plots.py` contains no
      `finished_at` and no comparison of `elapsed_s` with the budget. On the
      AC 1 truncated-trial tree and on the no-`finished_at` tree it returns 1,
      prints the same error, and writes no figure. Tests: one per guard in
      `tests/test_plots.py`.
- [ ] **7. plots.py's unique-crashes curve uses the Q4 rule and the Q10 cutoff.**
      `plots.trial_series(..., "unique_crashes")` (plots.py:53) currently builds
      the curve from every bucket `dedup.bucket_trial` returns, sentinels
      included. It must instead use the same buckets as aggregate's
      `unique_crashes`: sentinel buckets excluded (AC 5), buckets first seen
      after the budget excluded (AC 3(b)). Preferably both call one shared
      helper in aggregate.py, so the figure and the table cannot drift
      (ADR-0003 Consequences: "Unique crashes = the number of buckets whose key
      is not a sentinel ...", lead decision, 2026-11-15; AFL-033).

      Test: a trial with real-site buckets at 5 s and 50 s, a `no_stack` bucket
      at 20 s and a real-site bucket at 603 s (budget 600). Its unique-crashes
      series ends at 2. That equals the trial's `unique_crashes` from
      `load_trials`.

## Technical notes (architect)
- The guards and the cutoff live in aggregate.py, next to `main_campaign` and
  `load_trials`. plots.py imports them. That is the existing coupling: plots.py
  already imports `aggregate.trial_dirs` and `is_main_trial`.
- dedup.py stays unchanged: it still buckets every row (ADR-0003 "Ground-truth
  mapping": the cutoff is applied in aggregate, not in dedup).

## Test approach (tester)
Re-run the AFL-012 tester's truncated-campaign probe (AC 1) against aggregate and
plots. For each AC, kill a scratch mutant:
- guard removed;
- `significant` from raw p;
- `edges_auc` unclipped;
- `final_edges` from the last row;
- post-deadline bucket counted;
- sentinel bucket counted;
- the bound t taken from the wrong order statistic;
- plots counting all buckets.

Validity check: on one fixture, the figure's final unique-crash value equals
`trials.csv`'s `unique_crashes`.

## Log
- 2026-11-15 — created (req-engineer), from the lead decisions of 2026-11-15:
  - Q10: an execution that finishes after the deadline contributes to no
    endpoint. The PRD §8 sentence was added the same day.
  - Q3: report a lower bound for a median or quartile that cannot be
    determined.
  - Q4: unique crashes exclude the three sentinel buckets, which stay reported
    as separate counts. ADR-0003 has been updated; the PRD wording is proposed
    to the lead, not yet applied.
  - The tester's AFL-012 FAIL (truncated or unfinished main campaign analysed)
    and its surviving mutants (`significant` from raw p, unclipped
    `edges_auc`) are folded in here.
  - Analysis-only; must land before the 2026-11-19 analysis; not a pre-freeze
    item.
  - AC 7 (plots unique-crashes curve) added at the orchestrator's request.
- 2026-11-15 — PRD §8 "Crash dedup" sentence for Q4 approved and applied (unique crashes = distinct real crash sites within the budget; sentinel buckets excluded and reported separately); AC 3(d) default confirmed (lead decision, 2026-11-15) (orchestrator)
