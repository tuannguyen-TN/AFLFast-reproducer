---
id: AFL-031
title: Port the AFL-011 tester's scratch checks into the repo as stubbed tests
requirement: FR-7 / NFR-2 (AFL-011 ACs "Campaign timeout and concurrency from the config", "Initial corpus = S0", "Pre-flight symbolizer check", "Pilot + coverage-granularity fallback", "Pre-freeze checklist" (Waves and fillers), "≥3 targets (PRD §8)", "Baseline mode", "Abort stops running trials", "Smoke run kind")
paper_ref: Klees §methodology (fixed budget, identical conditions across arms); AFLFast (only the schedule differs between arms)
module: tests/test_run_campaign.py, harness/run_campaign.py (`execute` only)
depends_on: [AFL-011]
status: backlog
owner: developer
---

## Goal
The AFL-011 tester killed six runner mutants only with scratch checks that are not
in the repo (AFL-011, section "Test (tester, 2026-11-15)", "Mutation", and note T1).
Move those checks into `tests/test_run_campaign.py` as stubbed tests, so the
guarantees they pin (NFR-2 arm identity, `--timeout` from the config, the probe wave
barrier, the symbolizer timeout, the confirmation pilot's no-decision rule, the
non-empty override reason) cannot regress silently before the freeze. Also isolate
the `sysctl` exit-status case of test (e) (AFL-011 tester note T2).

Source: `test_tester_extra.py`
(the tester's scratch file, six test functions; outside the repo, read-only). It
imports `cfg_text`, `go`, `no_trials`, `rc`, `root` and `to_git` from
`test_run_campaign`; in the repo the tests sit in that file and use those helpers
directly.

## Acceptance criteria
Every test is stubbed: trial launches go through a stubbed `_launch` or a stubbed
`subprocess.run` for `fuzzer.cli` argvs, and the symbolizer pre-flight is stubbed
where it is not the subject. No real fuzzer trial runs, no real target binary is
executed by these tests, and none of them creates a trial directory outside pytest's
tmp. For each mutant below, the tester applies it in a scratch copy and confirms
that the named test fails on it and passes on the unmutated code.

- [ ] **`--timeout` passed to every trial.** For each run kind `first_pilot`,
      `main`, `probe` and `confirmation_pilot`, with `timeout_s: 3.25` in the
      test config (not the CLI's default 1.0), every launched `fuzzer.cli` argv has
      `--timeout 3.25` (and `--seconds` equal to the config's
      `seconds_per_trial`). Kills the mutant: `--timeout` dropped from `_launch`'s
      argv.
- [ ] **`--seeds` identical across arms (NFR-2).** In the same runs, every argv's
      `--seeds` is `<root>/targets/seeds/<target>`, and for every run kind except
      `probe`, the sorted UNIFORM argvs equal the sorted FAST argvs once
      `--schedule` and the arm's name in `--out` are normalised. `main` argvs carry
      a 40-character `--freeze-commit`; no other kind has one. Kills the mutant:
      the `--seeds` directory differing per arm.
- [ ] **Symbolizer pre-flight uses the config's timeout.** With `Executor`
      replaced by a stub that records its `timeout_s` and raises on `run`, a first
      pilot with `timeout_s: 4.75` constructs the executor with 4.75 only, and no
      trial directory exists. Kills the mutant: the symbolizer executor's timeout
      fixed at 1.0.
- [ ] **Confirmation pilot writes no decision.** A stubbed `confirmation_pilot`
      run exits 0 and no `granularity_decision*.json` exists anywhere under
      `results/`. Kills the mutant: the confirmation pilot writing a decision.
- [ ] **Probe waves are barriered; at most `concurrency` at once.** With
      `_launch` stubbed to record start and end times (each trial sleeps briefly),
      two targets and `concurrency: 3`: a first pilot never has more than 3 trials
      running at once and reaches 3; a probe also peaks at exactly 3, and the
      earliest start in wave 1 is not before the latest end in wave 0. Kills the
      mutant: probe trials submitted without a per-wave barrier.
- [ ] **Empty override reason refused.** `--allow-fewer-targets ""` and
      `--allow-fewer-targets "   "` on a two-target config each exit 2, the message
      contains "reason", and no trial directory exists. Kills the mutant: the
      empty-reason guard removed.
- [ ] **Concurrency equal to the core count proceeds.** With `physical_cpus`
      stubbed to 5, a probe with `concurrency: 6` exits 2 naming both numbers and
      creates no trial directory, and the same probe with `concurrency: 5` exits 0.
      This is the sixth scratch test; it pins the boundary and kills no mutant the
      repo suite misses.
- [ ] **T2: test (e)'s exit-status case isolated.** In
      `test_unusable_sysctl_refused` (AFL-011 AC "Campaign timeout and concurrency
      from the config", test (e)), the exit-status case is today
      `{"out": "", "rc_": 1}`, whose empty output is refused on its own, so the
      exit-status check is untested. Its stub instead prints a positive integer
      (e.g. `"8\n"`) and exits 1. The test asserts that the stub's printed output,
      stripped, is all digits and that its exit status is 1, so only the exit
      status can cause the refusal; then, as before, with `concurrency: 1` the
      runner exits 2, the message names `sysctl -n hw.physicalcpu`, and no trial
      directory exists. The other cases are unchanged. Kills the mutant: the
      `sysctl` non-zero-exit refusal removed (the one survivor of the AFL-011
      tester's 31 mutants).
- [ ] **Baseline/abort/smoke scratch tests ported (lead decision, 2026-11-15).**
      The tests in the AFL-011 tester's second scratch file
      `test_gaps.py`
      (outside the repo, read-only; AFL-011 Log, tester 2026-11-15) are in
      `tests/test_run_campaign.py`, each killing the mutant named:
      `test_baseline_probe_summary_label` (B2: the baseline label dropped from
      `probe_summary.json`); `test_dmax_refuses_baseline_json_directly` (B3: the
      `_dmax` baseline refusal removed; the repo test is masked by the dirty-tree
      refusal, this one calls `_dmax` directly); `test_abort_reaches_trial_grandchildren`
      (A1: `os.kill` instead of `os.killpg`); `test_grace_is_total_not_per_trial`
      (A2: the grace applied per trial instead of in total);
      `test_culprit_not_aborted_and_named_in_list` (A10: the culprit also marked
      `aborted`); `test_smoke_exit0_without_final_row_fails` (S4: smoke PASS
      without a final `metrics.csv` row). `test_smoke_output_invisible_to_aggregate`
      (smoke output, with and without `--out`, is not found by
      `aggregate.trial_dirs`, `main_campaign` or `is_main_trial`) is ported too;
      it kills no named mutant. In addition, a new test runs `--baseline` with
      `--kind smoke` and asserts exit 2, a message naming `--baseline`, and no
      trial directory; the existing guard in `_preflight` ("`--baseline` needs
      `--kind probe` or `--crash-probe`") stays as is. Kills mutant B10:
      `--baseline` accepted with `--kind smoke`
      (`if not (a.crash_probe or a.kind in ("probe", "smoke")):`), which survives
      both the repo suite and the scratch tests today. The A1 and A2 tests start
      stub trial scripts through `subprocess.Popen` (the `stub_trials` fixture or
      the scratch file's group stub), never `fuzzer.cli` or a target binary, and
      no stub process outlives the test.
- [ ] **`started` recorded before launch (lead decision, 2026-11-15).** Fixes the
      AFL-011 known defect (AFL-011 "Known gaps"; tester, 2026-11-15): when a
      runner exception (AFL-011 abort trigger (3)) is raised after a trial was
      launched but before its record was written, the exception handler in
      `execute` records the trial `{aborted: true, started: false}` although it
      ran. In `harness/run_campaign.py`, `_one` sets `started` on the trial's
      record (in `results`) before it calls `_launch`, so the handler's
      `setdefault` keeps that record. Such a trial is written with `started`
      true and still `aborted: true` (its record has no `returncode`, and the
      `aborted` mark is what lets AFL-012 exclude it). Trials that truly never
      started (abort set before `_one` reaches `_launch`, probe waves never
      submitted) still get `{aborted: true, started: false}`, as AFL-011's Abort
      AC requires. Regression test:
      `test_exception_after_trial_ran_is_not_recorded_never_started`, ported
      from the same scratch file: a first pilot whose stubbed `_launch` raises
      `RuntimeError` after the real launch of (uniform, seed 1007); that trial's
      `pid` file exists, its record's `started` is not `false`, and it carries
      `aborted: true` (the last assertion is added to the scratch test). It fails
      on today's code and passes after the fix. The existing abort tests
      (`test_runner_exception_aborts_all_trials`,
      `test_runner_exception_in_probe_wave_marks_later_waves_not_started` and the
      rest) still pass unchanged.
- [ ] **Pre-freeze.** This ticket is in `tickets/done/` before the AFL-011 freeze
      commit (AFL-011 "Pre-freeze checklist" item (a); lead decision, 2026-11-15).
- [ ] No change under `src/`, and under `harness/` only the change of AC
      "`started` recorded before launch" (`git diff` on `src/` is empty; on
      `harness/` it touches only `execute` in `run_campaign.py`: `_one` and, if
      needed for the `aborted` mark, its exception handler); otherwise tests
      only. (Amended 2026-11-15 for that AC, lead decision, 2026-11-15.)

## Technical notes (architect)
The scratch file is a starting point, not a spec: port its assertions, adapt to the
`tests/test_run_campaign.py` fixtures as they stand after AFL-011's baseline, abort
and smoke changes, and keep each test stubbed. If AFL-011 adds the smoke kind before
this lands, extending the `--timeout` and `--seeds` checks to it is welcome but not
required.

## Test approach (tester)
Run `pytest tests/test_run_campaign.py` (default markers). Apply each of the seven
named mutants (six from the AFL-011 tester's list, plus the `sysctl` exit-status
survivor), and the seven of the 2026-11-15 additions (B2, B3, A1, A2, A10, S4,
B10), in a scratch copy, under a stubbed `_launch`, and confirm the named test
fails and the unmutated code passes. Confirm `pgrep -fl 'fuzzer[.]cli'` is empty
after the run.

## Log
- 2026-11-15 — created from AFL-011 tester notes T1 and T2; must land before the AFL-011 freeze (checklist item (a)) (lead decision, 2026-11-15) (req-engineer)
- 2026-11-15 — scope added from the AFL-011 tester's 2026-11-15 PASS: AC "Baseline/abort/smoke scratch tests ported" (test_gaps.py tests killing B2, B3, A1, A2, A10, S4, plus the smoke-invisible-to-aggregate test, plus a new `--baseline --kind smoke` refusal test killing B10) and AC "`started` recorded before launch" (fix of the `started: false` defect in `_one`, regression test); "tests only" AC amended to allow that one harness change; both before the freeze (lead decision, 2026-11-15, orchestrator routing) (req-engineer)
- 2026-11-15 — both req-engineer additions accepted (record `started` correctly on abort while keeping `aborted: true`; `execute` changes in run_campaign.py allowed): they fix a known defect. AFL-031 changes runner code, so it gets an Opus review, and lands before the freeze per AFL-011 checklist item (a) (lead decision, 2026-11-15) (orchestrator)
