---
id: AFL-031
title: Port the AFL-011 tester's scratch checks into the repo as stubbed tests
requirement: FR-7 / NFR-2 (AFL-011 ACs "Campaign timeout and concurrency from the config", "Initial corpus = S0", "Pre-flight symbolizer check", "Pilot + coverage-granularity fallback", "Pre-freeze checklist" (Waves and fillers), "≥3 targets (PRD §8)", "Baseline mode", "Abort stops running trials", "Smoke run kind")
paper_ref: Klees §methodology (fixed budget, identical conditions across arms); AFLFast (only the schedule differs between arms)
module: tests/test_run_campaign.py, harness/run_campaign.py (`execute`; `main` probe dirty-tree refusal; `crash_probe` json fields; run-environment record in campaign.json and crash_durations.json)
depends_on: [AFL-011]
status: done
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

- [x] **`--timeout` passed to every trial.** For each run kind `first_pilot`,
      `main`, `probe` and `confirmation_pilot`, with `timeout_s: 3.25` in the
      test config (not the CLI's default 1.0), every launched `fuzzer.cli` argv has
      `--timeout 3.25` (and `--seconds` equal to the config's
      `seconds_per_trial`). Kills the mutant: `--timeout` dropped from `_launch`'s
      argv.
- [x] **`--seeds` identical across arms (NFR-2).** In the same runs, every argv's
      `--seeds` is `<root>/targets/seeds/<target>`, and for every run kind except
      `probe`, the sorted UNIFORM argvs equal the sorted FAST argvs once
      `--schedule` and the arm's name in `--out` are normalised. `main` argvs carry
      a 40-character `--freeze-commit`; no other kind has one. Kills the mutant:
      the `--seeds` directory differing per arm.
- [x] **Symbolizer pre-flight uses the config's timeout.** With `Executor`
      replaced by a stub that records its `timeout_s` and raises on `run`, a first
      pilot with `timeout_s: 4.75` constructs the executor with 4.75 only, and no
      trial directory exists. Kills the mutant: the symbolizer executor's timeout
      fixed at 1.0.
- [x] **Confirmation pilot writes no decision.** A stubbed `confirmation_pilot`
      run exits 0 and no `granularity_decision*.json` exists anywhere under
      `results/`. Kills the mutant: the confirmation pilot writing a decision.
- [x] **Probe waves are barriered; at most `concurrency` at once.** With
      `_launch` stubbed to record start and end times (each trial sleeps briefly),
      two targets and `concurrency: 3`: a first pilot never has more than 3 trials
      running at once and reaches 3; a probe also peaks at exactly 3, and the
      earliest start in wave 1 is not before the latest end in wave 0. Kills the
      mutant: probe trials submitted without a per-wave barrier.
- [x] **Empty override reason refused.** `--allow-fewer-targets ""` and
      `--allow-fewer-targets "   "` on a two-target config each exit 2, the message
      contains "reason", and no trial directory exists. Kills the mutant: the
      empty-reason guard removed.
- [x] **Concurrency equal to the core count proceeds.** With `physical_cpus`
      stubbed to 5, a probe with `concurrency: 6` exits 2 naming both numbers and
      creates no trial directory, and the same probe with `concurrency: 5` exits 0.
      This is the sixth scratch test; it pins the boundary and kills no mutant the
      repo suite misses.
- [x] **T2: test (e)'s exit-status case isolated.** In
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
- [x] **Baseline/abort/smoke scratch tests ported (lead decision, 2026-11-15).**
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
- [x] **`started` recorded before launch (lead decision, 2026-11-15).** Fixes the
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
- [x] **P3: probes refuse a dirty tree (lead decision, 2026-11-15).** In
      `harness/run_campaign.py` `main`, `--kind probe` runs and the crash probe
      (`--crash-probe`, including its `--baseline` form) refuse to start when the
      provenance `dirty` value is not `False` (that is, `True`, or unknown/`None`):
      the runner prints a Refusal message that names the dirty tree, exits 2 like the
      existing main-campaign refusal, and creates no trial directory and no
      `crash_durations.*` file. Today only the main campaign refuses a dirty tree
      (the `if a.kind == "main" and not a.crash_probe:` block); probes only record
      `dirty`. This enforces AFL-011's probe condition "committed code with a clean
      tree". The pilot kinds (`first_pilot`, `confirmation_pilot`) are NOT in scope
      (the decision names probe runs and the crash probe only), and the main campaign
      refusal is unchanged. Tests in `tests/test_run_campaign.py`, stubbed (no real
      trial, no target binary run): with `_provenance` stubbed to return dirty `True`
      and again `None`, each of `--kind probe`, `--crash-probe` and
      `--crash-probe --baseline` exits 2 with the message and no output; with dirty
      `False` each proceeds as before (exit 0 under the existing stubs); and a pilot
      kind with dirty `True` is not refused for dirtiness (pins the scope).
- [x] **Crash-probe config record (lead decision, 2026-11-15).**
      `crash_durations.json` also records `config_path` (the config file's
      repo-relative path), `config_sha256` (the SHA-256 of that file's bytes, hex) and
      `timeout_s` (the value passed to the floor check, `cfg.timeout_s`), in addition
      to the fields it records today (`commit`, `dirty`, `concurrency`, `R`,
      `probe_timeout_s`, `hw_physicalcpu`, `bugs`, `D_max`, `D_max_bug`). Test in
      `tests/test_run_campaign.py`, stubbed: a crash probe on a test config with
      `timeout_s: 3.25` writes a `crash_durations.json` whose `config_path` is the
      repo-relative path, whose `config_sha256` equals `hashlib.sha256` of the file's
      bytes, and whose `timeout_s` is 3.25; the same three fields appear for
      `--baseline`; the existing fields are unchanged.
- [x] **Run-environment record (lead decision, 2026-11-15).** Every run's
      `campaign.json`, and every `crash_durations.json`, also records (1) the state of
      both macOS crash reporters, the per-user agent `gui/<uid>/com.apple.ReportCrash`
      and the system daemon `system/com.apple.ReportCrash.Root`: for each, whether it
      is loaded (the `launchctl print <service>` exit status, 0 = loaded) and whether
      it is disabled (from `launchctl print-disabled gui/<uid>` and
      `launchctl print-disabled system`); and whether any `ReportCrash` process
      exists (`pgrep -x ReportCrash`), taken at the run's start and again at its end;
      and (2) `hw_perflevel0_physicalcpu` and `hw_perflevel1_physicalcpu`
      (`sysctl -n hw.perflevel0.physicalcpu` / `hw.perflevel1.physicalcpu`) next to
      the existing `hw_physicalcpu`. The record never stops a run. Test in
      `tests/test_run_campaign.py`, stubbed (no real `launchctl`, `pgrep` or `sysctl`
      call): the keys are present with the stubbed values in both files, for a
      probe, a crash probe and `--baseline`; and each value is `null` where its
      command is absent or fails.
- [x] **Pre-freeze.** This ticket is in `tickets/done/` before the AFL-011 freeze
      commit (AFL-011 "Pre-freeze checklist" item (a); lead decision, 2026-11-15).
- [x] No change under `src/`, and under `harness/` only the changes of ACs
      "`started` recorded before launch", "P3", "Crash-probe config record" and
      "Run-environment record"
      (`git diff` on `src/` is empty; on `harness/` it touches only `run_campaign.py`:
      in `execute`, `_one` and, if needed for the `aborted` mark, its exception
      handler; in `main`, the dirty-tree refusal for probes; in `crash_probe`, the
      added `crash_durations.json` fields and the arguments it needs; and the
      run-environment record wherever `campaign.json` and `crash_durations.json` are
      written); otherwise tests only. (Amended 2026-11-15 for these ACs, lead
      decision, 2026-11-15.)

## Technical notes (architect)
The scratch file is a starting point, not a spec: port its assertions, adapt to the
`tests/test_run_campaign.py` fixtures as they stand after AFL-011's baseline, abort
and smoke changes, and keep each test stubbed. If AFL-011 adds the smoke kind before
this lands, extending the `--timeout` and `--seeds` checks to it is welcome but not
required.

P3 and the config record: the refusal belongs next to the main-campaign block in
`main` (after `_provenance()`, before `check_symbolizer`); the new JSON fields are
written in `crash_probe` (the `crash_durations.json` `_write_json` call), which needs
the config path passed in; hash the file's bytes, not its parsed form.

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
- 2026-11-15 — added ACs: probe and crash-probe refuse a tree whose `dirty` is not False (P3), and crash_durations.json records the config path, its SHA-256 and timeout_s; scope widened to these run_campaign.py changes. Until AFL-031 lands, any probe's numbers are used only after checking `dirty` is false in that probe's metadata, recorded in AFL-011's Log (lead decision, 2026-11-15) (req-engineer)
- 2026-11-15 — added AC "Run-environment record": both crash reporters' state (per-user agent and system daemon: loaded, disabled, a ReportCrash process at start and end) and the performance and efficiency core counts in campaign.json and crash_durations.json; scope AC amended to allow it (lead decision, 2026-11-15) (orchestrator)
- 2026-11-15 — implemented (developer). Harness (run_campaign.py only): `_one` records `started: true` before `_launch` and the exception handler marks launched-but-unrecorded trials `aborted`; probe/crash-probe refuse `dirty is not False` (P3); `crash_durations.json` gains `config_path`, `config_sha256`, `timeout_s`; `perf_cores()` / `crash_reporters()` add `hw_perflevel{0,1}_physicalcpu` and `crash_reporters.{start,end}` to `campaign.json` and `crash_durations.json`. Tests: `tests/test_run_campaign.py` (scratch ports use a faked `Popen` for fuzzer.cli since `_launch` no longer uses `subprocess.run`; the `root` fixture now stubs `_cmd`; existing probe/crash-probe tests adapted to P3 via `clean_unknown` or committing the config before the run). 19 mutants applied by hand in the real file (then restored): all killed. `disabled` is null when the label is not listed by `launchctl print-disabled`. Ready for Opus review; Pre-freeze AC left open for the lead.
- 2026-11-15 — review: changes requested, back to in-progress (bounce 1). Must-fix R1-R3 below; harness logic for `started`/`aborted`, P3 and the config record verified, 16 hand mutants killed in a scratch copy. Gates: ruff clean, mypy src clean, pytest tests/test_run_campaign.py 147 passed. (reviewer)

## Review (reviewer, 2026-11-15)

Must-fix:
- R1 (AC preamble "Every test is stubbed" + AC "Empty override reason refused"): `test_allow_fewer_needs_nonempty_reason` stubs neither `check_symbolizer` nor `_launch`. On the empty-reason-guard mutant the `"   "` case passes preflight and runs the real symbolizer on the real binaries and a real 12-trial first pilot; the `""` case alone does not kill the mutant (checked: it survives, because `check_targets`' own refusal text contains `"<reason>"`). Fix: stub `check_symbolizer` and `_launch` as the neighbouring tests do, and assert the guard's own text (`"non-empty reason"`) so each case kills the mutant on its own.
- R2 (AC "Run-environment record": "The record never stops a run"): `perf_cores`, `_disabled` and `crash_reporters` catch only `OSError`. Undecodable output (`UnicodeDecodeError`, a `ValueError`, from `text=True`) or a `SubprocessError` still escapes, and the end-of-run sample sits between the granularity-decision write and the final `campaign.json` write: an escape there loses `finished_at` (AFL-033 then refuses the main campaign). Fix: catch `(OSError, ValueError, subprocess.SubprocessError)` in the three helpers, returning null, with one stubbed test case (a `_cmd` raising `UnicodeDecodeError` gives nulls and the run exits 0).
- R3 (AC "Run-environment record", null rule; needs a lead decision): `disabled` is null when `launchctl print-disabled` succeeds but does not list the label. The AC says a value is null where its command is absent or fails, which is not the case here. Null then means both "could not tell" and "no override", and a reader can't tell which. Recommendation: unlisted gives `false` (no disable override in launchd's database, so launchd's default applies; `loaded` records the effective state), and null only when the command fails. If the lead prefers null, amend the AC's null rule.

Should-fix / nits (not blocking):
- `config_sha256` is computed after the probe from the file as it is then. Hash the bytes in preflight, the bytes actually parsed. Note that P3's dirty check ignores untracked files, so an untracked config passes it.
- The main-campaign refusal text now carries `(dirty=...)`. Behaviour is unchanged and AFL-011 AC (a) is still met (it lists the modified tracked files), so accept it or revert it.
- The `start` sample is taken after `check_symbolizer`, which crashes every bug's trigger once, so `process: true` at start can be caused by the runner itself. Say so wherever the record is interpreted.
- `_cmd` has no timeout, so a wedged `launchctl` would hang the run at the end-of-run sample.
- The A1 test's `Popen` lambda reroutes every `Popen` (including git in `_provenance`) to the stub script. Filter on the `fuzzer.cli` argv as `run_argvs` does.
- In `_one`, the AFL-031 comment sits above the abort check, not above the pre-launch record.
- 2026-11-15 — review bounce 1 fixed (developer): R1 `test_allow_fewer_needs_nonempty_reason` now stubs `check_symbolizer` and `_launch` and asserts "non-empty reason" (each case alone kills the guard-removed mutant, checked in scratch); R2 `perf_cores`/`_disabled`/`crash_reporters` catch `ENV_ERRORS = (OSError, ValueError, SubprocessError)` and `_cmd` has a 10 s timeout (`test_cmd_has_timeout`; `test_run_environment_recorded` gains `raise` (UnicodeDecodeError) and `timeout` modes, which also assert `finished_at`); R3 `disabled` is false when `print-disabled` succeeds without the label, null only when the command fails (new `unlisted` mode); nit: the A1 test's `Popen` stub routes only fuzzer.cli argvs; nit: `started` comment moved above the pre-launch record. Other should-fixes left for the lead.
- 2026-11-15 — re-review after bounce 1: approved, moved to testing. R1-R3 fixed and verified. In a scratch copy, 21 mutants were each killed by an assertion: the 16 from the first review, plus 5 new ones (`ENV_ERRORS` reverted to `OSError` in `crash_reporters`, `perf_cores` and `_disabled`; no `_cmd` timeout; unlisted gives null). Each empty-reason case now kills the guard-removed mutant on its own. Gates: ruff clean, mypy src clean, pytest tests/test_run_campaign.py 160 passed. Side effect: `physical_cpus` and `_first_line` catch only `OSError`, so a `sysctl`/`sw_vers`/`clang` call that times out at preflight or at the `machine()` record ends the run with a `TimeoutExpired` traceback before any trial or output exists. Before the timeout it would hang. Not a must-fix (no data affected, and the run still refuses to start); should-fix: turn `SubprocessError` into a Refusal in `physical_cpus` and into "unknown" in `_first_line`. Nit: `_disabled` maps any token other than disabled/true to `false`. (reviewer)
- 2026-11-15 — test: PASS, ready for the crew-lead's gated close; `status:` stays `testing` (README defines no separate ready-to-close value). Gates: ruff clean, mypy src clean, pytest tests/test_run_campaign.py 160 passed (30 s), full default suite 569 passed, 4 deselected (108 s); no flake, no re-run needed. Every AC's named test exists and its assertions match. Three mutants applied in a scratch copy, each killed: empty-reason guard removed (both `test_allow_fewer_needs_nonempty_reason` cases fail); P3 probe dropped from the refusal (`test_probes_refuse_dirty_or_unknown_tree[...-True]` and `[...-None]` fail), and P3 `None` allowed (the `-None` cases fail for all three arg sets); `ENV_ERRORS` reduced to `OSError` (8 `test_run_environment_recorded` cases fail). Validity: `src/` is untouched by AFL-031 (its diff is AFL-034's hit/bucket change); the arms differ only in schedule (`test_arms_identical_except_schedule_nfr2`); `_cmd` is stubbed in the `root` fixture and in the environment tests, so no real launchctl, pgrep or sysctl runs; no home or scratch path in the added lines of run_campaign.py or test_run_campaign.py; `pgrep -fl 'fuzzer[.]cli'` is empty. "Pre-freeze" AC left unticked for the lead. (tester)
- 2026-11-15 — closed (crew-lead): DoD verified; gated move to done; Pre-freeze met by closing before the AFL-011 freeze commit.
