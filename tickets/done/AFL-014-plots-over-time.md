---
id: AFL-014
title: Plots — coverage/crash over time + variance
requirement: FR-8
paper_ref: Klees § statistically sound comparisons (report variance across trials, not single runs)
module: harness/plots.py
depends_on: [AFL-011]
status: done
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
- [x] Reads persisted per-trial metrics from a results directory
      (`python harness/plots.py results/`). It runs no fuzzing itself.
- [x] For each target it writes a coverage-over-time figure (edges vs wall-clock).
- [x] For each target it writes a unique-crashes-over-time figure (deduped
      crashes vs wall-clock).
- [x] Each figure shows UNIFORM and FAST together, each with a median line and an
      inter-trial variance band.
- [x] Figures are written to files under `results/`.
- [x] Aborted main campaign refused (Q11; lead decision, 2026-11-15): `plots.main` returns 1 with
      aggregate's "recorded aborts" error and writes no figures. Tests:
      test_aborted_main_campaign_refused_per_trial_marker,
      test_aborted_main_campaign_refused_campaign_level_null_trial.

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
- 2026-11-15 — in-progress (developer). Started although depends_on AFL-011 is not closed (lead decision, 2026-11-15); built against the layout the working-tree run_campaign.py / fuzzer.py write.
- 2026-11-15 — to review (developer). Implemented harness/plots.py, tests/test_plots.py, fixtures tests/fixtures/plots/.
  - AC1 reads results dir, no fuzzing: main() uses aggregate.trial_dirs; test_both_figures_both_arms_nonanalysed_excluded.
  - AC2/3 two figures per target at <results>/figures/<target>_coverage.png and _unique_crashes.png: same test; test_crash_series_is_step_from_zero.
  - AC4 both arms, median + IQR band, legend n: test_plot_metric_median_and_iqr_per_arm.
  - AC5 files under results/figures/.
  - Non-analysed runs excluded via aggregate.is_main_trial (campaign.json kind == main); test_is_analysed_uses_campaign_kind.
  - Open confirmations: 1 s grid 0..seconds, carry-forward; IQR band; TTFC plot skipped; bare runs with no campaign.json are not plotted.
- 2026-11-15 — review (reviewer): **BOUNCE → in-progress** (one required change, R1). Code is correct against all five ACs; the bounce is for a test that does not exercise AC3's "deduped".
  - Gates: `ruff check harness/plots.py tests/test_plots.py` clean; `mypy src` clean; `pytest tests/test_plots.py` 7 passed. `mypy harness/plots.py` reports no errors in plots.py (the errors shown are in aggregate.py/dedup.py, AFL-012 WIP, not counted here).
  - AC1 (reads results dir, no fuzzing) — met. plots.py:94-102 `main` → `aggregate.trial_dirs` → `plot_all`; nothing imports the executor or fuzzer loop. Evidence: test_both_figures_both_arms_nonanalysed_excluded.
  - AC2 (coverage figure per target) — met. plots.py:44-47 edges from metrics.csv (`elapsed_s`, `edges`); plots.py:86-90 one figure per target per metric.
  - AC3 (unique crashes = deduped crashes vs time) — code met, test not. plots.py:48-49 uses `dedup.bucket_trial(...).first_elapsed_s` (crash-site buckets, ADR-0003), step from 0 at t=0: honest dedup, and the same definition as aggregate `unique_crashes` (all buckets, sentinels included). But no fixture has two events at the same crash_site (fixtures s2, s4 have site0+site1, s1/s3 one event, s5 none), so replacing buckets with raw crash_events rows passes every test. **R1 (required):** add a repeat-site event to a fixture (e.g. `3.0,…,site0` in main/tlv_parser/uniform/s2/crash_events.csv) so test_crash_series_is_step_from_zero still expects [0,1,2] and would fail on raw counting.
  - AC4 (both arms, median line + inter-trial variance band) — met. plots.py:63-72 percentiles 25/50/75 across trials on a shared 1 s grid, `fill_between` IQR, legend `UNIFORM (n=…)` / `FAST (n=…)`. Test asserts labels, 2 bands, final median 8.5 (test_plots.py:52-69). Klees variance requirement satisfied; median, not mean.
  - AC5 (files under results/) — met. plots.py:88 `<results>/figures/<target>_{coverage,unique_crashes}.png`; test asserts parent dir.
  - Invariants: no change under src/ (NFR-2 and blind mutation untouched). Deterministic: no RNG, no wall-clock in output. Agg backend set before pyplot import.
  - Open confirmations: (1) 1 s grid 0..seconds, carry-forward — accept. (2) IQR band — accept (matches aggregate median+IQR, PRD §8). (3) TTFC plot skipped — accept (SC5 asks for coverage and crashes only; adding one needs Vision/PRD). (4) Trials without campaign.json not plotted — accept: run_campaign.py always writes campaign.json with `kind` before any trial, so plots and stats use the same main-campaign trial set, which is what Klees needs; bare `fuzzer.cli` demo runs are not pre-registered data.
  - Edges before the first sample = first value (plots.py:36-39): accept, not fabrication. fuzzer.py ticks the first metrics row right after the first S0 execution (milliseconds after the monotonic start, under one grid step), both arms get the same treatment, and plotting 0 at t=0 would draw a 0→S0 ramp over the first second, which is no more truthful. It differs from `aggregate.edges_auc` ("0 before the first row"); the numeric gap is negligible. **R3 (recommended):** say so in the module docstring.
  - Recommended, non-blocking: **R2** — `main` exits 0 and prints nothing when no main trial is found (wrong dir, or a results dir of bare runs); print a stderr note or return non-zero. **R4** — an empty metrics.csv raises a bare IndexError in `resample`; aggregate raises a clear ValueError for the same case. **R5** — test_both_figures calls `plot_all(load(FIX), tmp_path/results)`: the trials are not under results_dir, so `is_main_trial` finds campaign.json only because `_campaign` walks past `top` when it never meets it. Prefer copying FIX into tmp_path and calling `main([tmp])`, which also covers AC1's CLI form.
  - Coupling: plots depends on `aggregate.trial_dirs(results_dir) -> list[(Path, dict)]` and `aggregate.is_main_trial(trial_dir, results_dir) -> bool` (AFL-012, in progress). A signature change there breaks plots.py:84/100 and test_plots.py:48-49; AFL-012 should keep both or update plots in the same change.
- 2026-11-15 — back to review (developer), bounce fixes: R1 repeat event `3.0,...,site0` added to fixture uniform/s2 (test_crash_series_is_step_from_zero still expects [0,2,4]/[0,1,2]; raw counting would give 3 steps); R2 main() prints stderr note, returns 1 with no main trial (test_main_no_main_trial_exits_nonzero); R3 module docstring states before-first-sample convention vs aggregate.edges_auc; R4 empty metrics.csv raises ValueError (test_empty_metrics_csv_is_clear_error); R5 test_main_writes_both_figures_nonanalysed_excluded copies FIX into tmp_path and calls main([dir]). ruff/mypy clean, tests/test_plots.py 9 passed.
- 2026-11-15 — re-review (reviewer): **APPROVE → testing.** All five ACs met; R1 (required) fixed; R2–R5 done.
  - Gates: `ruff check harness/plots.py tests/test_plots.py` clean; `mypy src` clean; `mypy harness/plots.py` reports nothing in plots.py (remaining errors are AFL-012's aggregate.py and dedup's untyped import); `pytest tests/test_plots.py` 9 passed (run after another agent's full pytest, pid 48798, exited).
  - R1: fixtures/plots/main/tlv_parser/uniform/s2/crash_events.csv now has a repeat site0 event at 3.0; test_crash_series_is_step_from_zero still expects [0,1,2] at times [0,2,4], so counting raw events (3) would fail it. AC3's "deduped" is now exercised. Nit, not blocking: that row and the site1 row both have execs=2.
  - R2: plots.py `main` returns 1 with a stderr note when no main trial is found; test_main_no_main_trial_exits_nonzero.
  - R3: module docstring plots.py:9-11 states the before-first-sample convention and the edges_auc difference.
  - R4: plots.py:50-51 raises ValueError on an empty metrics.csv; test_empty_metrics_csv_is_clear_error.
  - R5: test_main_writes_both_figures_nonanalysed_excluded copies the fixtures into tmp_path and calls `plots.main`. That covers AC1's CLI form with the trials under results_dir. Pilot exclusion is still exercised: the pilot trial has no metrics.csv, so it would raise if plotted.
  - Coupling (unchanged): plots and its tests now call `aggregate.trial_dirs` and `aggregate.is_main_trial` for real; AFL-012 must keep both signatures or update plots in the same change.
- 2026-11-15 — test (tester): **PASS. Ready for crew-lead close.** Tested in an isolated copy of the working tree (rsync excluding .venv, results/, .git) under the job scratch dir, using the repo .venv with PYTHONPATH set to the copy's src. After testing, harness/plots.py, aggregate.py, dedup.py, tests/test_plots.py and fixtures/plots were byte-identical to the working tree.
  - Gates: `ruff check harness/plots.py tests/test_plots.py` clean (copy and repo); `mypy src` clean; `mypy harness/plots.py` shows no errors in plots.py (the 3 errors are missing pandas/scipy stubs in aggregate.py and the untyped fuzzer import in dedup.py, not this ticket's); `pytest tests/test_plots.py` 9 passed (copy and repo). Each pytest run started only after the pgrep load check showed no other pytest running.
  - AC1 (reads the results dir, no fuzzing) — PASS. `python harness/plots.py <copy of fixtures>` exits 0 and prints the two figure paths. I took a shasum snapshot of every file before and after the run: the only change is the two added PNGs, and no input was modified. plots.py imports only aggregate and dedup, not the executor or the loop.
  - AC2 (coverage figure per target) — PASS. `figures/tlv_parser_coverage.png`: x = "wall-clock time (s)", y = "edges covered". Values checked by hand: the FAST final median is 14 (edges 13/14/16), with an IQR band of 13.5–15; the UNIFORM final median is 8.5, with an IQR band of 8.25–8.75.
  - AC3 (deduped unique crashes per target) — PASS. `figures/tlv_parser_unique_crashes.png`: y = "unique crashes (deduped)", step from 0 at t=0. At t=3 the UNIFORM median is 1.0. Raw counting would give 1.5 there, because s2 has a repeat site0 event at 3.0. Crashes come from dedup.bucket_trial, so the same definition as aggregate unique_crashes is used.
  - AC4 (both arms, median line + inter-trial band) — PASS. Both arms are on the same axes (blue UNIFORM, red FAST), the legend reads `UNIFORM (n=2)` / `FAST (n=3)`, and a translucent IQR band is visible for each arm on both figures. The plotted values match hand-computed medians and 25/75 percentiles, not means and not min/max.
  - AC5 (files under results/) — PASS. The output is only `<results>/figures/<target>_{coverage,unique_crashes}.png`, and the before/after snapshot shows no other writes.
  - Non-main runs excluded (validity): I built a results dir with main (5 trials), plus a smoke/ run, a probe/<commit>/ run (kind probe), a pilot/first_pilot run, a bare `demo/` run with no campaign.json, and a 6th FAST main trial marked `"aborted": true` in main/campaign.json. All the extras are copies of real data. The figures are byte-identical to the 5-trial fixture run, so all of them are excluded. Negative control: removing the aborted marker gives `FAST (n=4)`, so the exclusion is real. Running twice gives identical PNG hashes (deterministic).
  - Mutation (scratch copy, tests/test_plots.py): killed — M1 raw crash_events counting instead of dedup buckets (test_crash_series_is_step_from_zero), M2 no fill_between band, M4 no is_main_trial filter, M5 output outside figures/, M6 single trial per arm, M7 no n in legend, M8 FAST arm only. **Survived — M3 mean instead of median** (the asserted UNIFORM n=2 final value is 8.5 under both), **M9 min/max band instead of IQR** (the test counts bands but does not check their edges). The code is correct on both points, as the hand-checked figure values above show. This is a test-strength gap, not a defect.
  - Recommended, non-blocking (lead's call): add assertions on the FAST arm in test_plot_metric_median_and_iqr_per_arm — final median == 14 (the mean would be 14.33) and final band == (13.5, 15) via `ax.collections[1]` (min/max would be 13/16). That kills M3 and M9. Cosmetic: the step series are drawn with linear interpolation between 1 s grid points (`ax.plot`, not `drawstyle="steps-post"`). On a 600 s campaign this is invisible, and it is not a correctness issue. An arm with zero main trials is skipped silently (a one-arm figure). This is acceptable because aggregate/run_campaign guarantee both arms.
  - Coupling: tested against the current working-tree aggregate.py (AFL-012 is now back in in-progress). If AFL-012 changes `trial_dirs` / `is_main_trial`, re-run tests/test_plots.py before closing either ticket.
- 2026-11-15 developer: AFL-014 test-strength fix per tester's M3/M9 note. test_plot_metric_median_and_iqr_per_arm now asserts FAST final median == 14 and FAST IQR band end edges == [13.5, 15] (from ax.collections[1] path vertices). Verified in scratch copies: mean-for-median (M3) and min/max band (M9) each fail only this test; unmodified code passes tests/test_plots.py (9 passed). No harness change; status unchanged.
- 2026-11-15 — crew-lead: close HELD, stays in testing (status unchanged, AC boxes not ticked). All five ACs are evidenced (reviewer APPROVE, tester PASS, M3/M9 now killed), so the code is not the issue. Blocker is depends-on-unaccepted-code: plots.py calls `aggregate.trial_dirs` and `aggregate.is_main_trial`, which do not exist in HEAD (HEAD harness/aggregate.py has no functions) and exist only in AFL-012's uncommitted working tree, which is back in review after bounce 1. Its B1 fix changed `_aborted`, which both functions call, after this ticket's tester ran (aggregate.py mtime 10:44:52). DoD needs ACs verified on a clean checkout, and AFL-014 cannot pass that alone. Close AFL-014 right after AFL-012 closes: re-run tests/test_plots.py against the accepted aggregate.py (the done-gate hook's full pytest does this), then tick ACs and move. depends_on AFL-011 is NOT a blocker: AFL-011 stays in testing until the freeze by design, and the layout plots.py reads (run.json, metrics.csv, crash_events.csv, campaign.json kind) is implemented (lead decision, 2026-11-15).
- 2026-11-15 — crew-lead: hold re-confirmed after the usage-limit pause (13:08). AFL-012 is still open: its tester FAILed it (second bounce, now with the lead) on an exclusion hole. A main campaign that aborts without a record (no `finished_at`, no `aborted` entry) has its truncated trials analysed. plots.py selects trials through the same `aggregate.trial_dirs` and `is_main_trial`, so it has the same hole, and the AFL-012 fix may change those functions or add a completeness check that plots should share. Close AFL-014 after AFL-012 closes: confirm that plots.py uses the final exclusion rule, and add a test if needed. The depends_on AFL-011 judgement is unchanged and is not a blocker.
- 2026-11-15 developer: Q11 folded in (lead decision, 2026-11-15). plots.plot_all calls `aggregate.main_campaign(results_dir)` (AFL-012's function, not a copy); plots.main catches ValueError, prints `error: ...` to stderr, returns 1. Two new tests in tests/test_plots.py (per-trial marker, campaign-level null-trial); happy path covered by the unchanged test_main_writes_both_figures_nonanalysed_excluded. AFL-033 guards not added. Status unchanged (testing).
- 2026-11-15 developer: Q11 checks run. pytest tests/test_plots.py tests/test_aggregate.py: 44 passed. In-memory mutant (aggregate.main_campaign no-op, plugin in job scratch): both test_aborted_main_campaign_refused_* tests FAIL (plots wrote figures, main returned 0). ruff clean, mypy src clean. No code change.
- 2026-11-15 — test (tester): **PASS (Q11 re-test). Ready for crew-lead close.** Scratch tree = HEAD archive + working-tree harness/aggregate,dedup,plots, tests, fixtures, ground_truth/triggers, src/fuzzer, pyproject; pytest test_plots+test_aggregate+test_dedup: 53 passed, 3 deselected (test_dedup adr_0003_content, real_tlv_run_every_real_bucket_has_example, crash_site_process_invariant need targets/bin binaries or docs absent from scratch; no build). Mutant (no-op aggregate.main_campaign, scratch plugin): both test_aborted_main_campaign_refused_* FAIL, other 9 pass. CLI on scratch fixtures: per-trial aborted marker -> rc 1, 'error: ... recorded aborts; it is not analysed' on stderr, no figures dir; good main fixture -> rc 0, both PNGs written. ACs 1-5 and Q11 AC: PASS. Note: plots.main catches every ValueError (incl. the empty-metrics.csv one), prints error, returns 1; acceptable, message is surfaced and exit is non-zero.
- 2026-11-15 — crew-lead: CLOSED. AFL-012 is in done; Q11 AC ticked; ACs 1-5 ticked on reviewer APPROVE + tester PASS (incl. Q11 re-test on a scratch tree with AFL-012 changes: 53 passed, mutant killed, CLI rc 1/rc 0 checked) (lead decision, 2026-11-15). INDEX row has no status column, unchanged.
- 2026-11-15 — closed by rm, gates re-run manually: ruff/mypy/pytest pass (ruff clean, mypy src clean, pytest 491 passed, 4 deselected). Standing rule: every close goes through the gated move; if one does not, re-run the gates and log it (lead decision, 2026-11-15) (orchestrator)
