---
id: AFL-011
title: Campaign runner — N trials × targets × schedules (Klees backbone)
requirement: FR-7
paper_ref: Klees §methodology (repeated trials, fixed budget, seeds)
module: harness/run_campaign.py, experiments/configs/main.yaml (timeout_s, concurrency), src/fuzzer/fuzzer.py (CSV line buffering only)
depends_on: [AFL-007, AFL-009, AFL-010, AFL-016]
status: testing
owner: developer
---

## Goal
Run the comparison the way Klees requires: many independent trials per condition,
fixed wall-clock budget, distinct recorded seeds, persisted time-series metrics.

## Acceptance criteria
- [ ] Reads `experiments/configs/main.yaml`.
- [x] Runs ≥10 trials per (target × schedule); trial i uses `base_seed + i`.
      **Cap (human decision, 2026-11-13):** in every run kind (main campaign,
      first pilot, probe, confirmation pilot, restarted first pilot, restarted
      confirmation pilot; the last two added, human decision, 2026-11-14; smoke
      run, lead decision, 2026-11-15) the
      number of trials per (target,
      schedule) is below 1000, so the seed ranges of the freeze AC's "Seeds"
      bullet cannot meet. Before any trial, the runner exits non-zero, with a
      message naming the run kind, the count and the cap, and creates no trial
      directories, if a config asks for 1000 or more. Test: a config with 1000
      main-campaign trials per (target, schedule) exits non-zero with no trial
      directories; 999 passes this check.
- [x] **Seed sets disjoint, checked at campaign start (human decision,
      2026-11-13).** At the start of every campaign (main, any pilot, a
      probe run, or the smoke run, lead decision, 2026-11-15), before any
      trial, the runner builds the full seed set of
      each run kind of the freeze AC's "Seeds" table (main campaign, first
      pilot, probe including fillers, confirmation pilot, restarted first
      pilot, restarted confirmation pilot; the last two added, human decision,
      2026-11-14; smoke run, lead decision, 2026-11-15) from the config, and
      exits non-zero, creating no trial directories, if any two sets share a
      seed. The message names both run kinds and one shared seed. There is no
      override flag. Rationale: the cap of 1000 trials prevents the expected
      overlap, and this direct check catches any overlap, including one from a
      future change to a range. Test: with the ranges changed in the test so
      that two sets overlap (e.g. the probe's offset set to 1000, or a range
      override in a test config), the runner exits non-zero, the message names
      both run kinds, and zero trial directories exist; the real ranges pass.
- [ ] Each trial honours `seconds_per_trial` and writes a per-trial metrics file
      (edges-over-time, unique-crashes-over-time, time-to-first-crash).
- [ ] Each result records commit hash + exact command (NFR-1).
- [ ] Re-running a trial with the same seed and the same `max_execs` stop reproduces
      its exec-indexed metrics and crash-event streams exactly, in every column
      except the wall-clock fields `elapsed_s` and `metrics.csv`'s `hang_time_s`,
      per AFL-007 / ADR-0005 §3 (replay on the exec index; timeouts are the one
      disclosed timing-dependent exception). A
      trial stopped by the wall-clock budget is not required to replay beyond the
      exec index it reached.
- [ ] Per-trial metrics also record `distinct_path_ids` (count of distinct
      `coverage.path_id` values over clean and crash executions; hang executions
      are never counted, because the loop does not read a hang's edges, AFL-007 /
      ADR-0005 §5) and `corpus_size`, both final and over time.
- [x] **Partial streams survive an external kill (human decision, 2026-11-13).**
      This AC changes `src/fuzzer/fuzzer.py`; AFL-007 is closed, so the change
      is made here. Source: the AFL-007 tester found that `_Recorder._open`
      (`src/fuzzer/fuzzer.py:103`) opens `metrics.csv` and `crash_events.csv`
      with default buffering, and nothing is flushed until `close()`. A trial
      killed from outside (SIGKILL, an aborted campaign) never reaches
      `close()` and loses rows it had already produced.
      - **Change.** Both files are opened line-buffered (`buffering=1`), so each
        row reaches the file when its `writerow` returns, and both are flushed
        and closed when the run ends (`run()`'s `finally`, as today). Nothing
        else in `fuzzer.py` changes: the columns, the row rules (ADR-0005 §6)
        and the replay guarantee are unchanged.
      - **Tests.** (a) A child Python process calls `fuzzer.run(cfg)` on
        `targets/bin/toy_parser` with a `seconds` budget far longer than the
        test (e.g. 60 s). The test polls `metrics.csv` until it holds at least
        one data row on disk, with a deadline of a few seconds (under default
        buffering it holds none before `close()`), then sends SIGKILL. After
        the kill, `metrics.csv` and `crash_events.csv` each parse with `csv`,
        start with their header row, and every data row has exactly the
        header's field count; `metrics.csv` has at least one data row.
        (b) The existing AFL-007 tests in `tests/test_fuzzer.py` still pass
        unchanged.
- [ ] **Pilot + coverage-granularity fallback (pre-registered, ADR-0001).** A pilot
      mode runs 3 trials per (target × schedule) at the main `seconds_per_trial`, with
      seeds `base_seed + 1000 + i` (disjoint from main trials), writing to
      `results/pilot/`; pilot results are excluded from AFL-012 analysis. Decision
      rule, evaluated on the pilot before the main campaign (or, after a
      restart, on the restarted first pilot, only if the fallback has not
      already fired; AC "Pre-registered target retuning rule and freeze",
      "Limit", human decision, 2026-11-14), pooled over both arms,
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
      - **Target freeze.** The target retuning rule, the confirmation pilot and
        the freeze point are in the next AC, "Pre-registered target retuning rule
        and freeze". The re-run of the pilot mentioned above *is* that AC's
        confirmation pilot. It is never used to re-evaluate this trigger.
- [ ] **Pre-registered target retuning rule and freeze (human decision,
      2026-11-07; fixed before any pilot data exists).**
      - **Scope.** Every deep planted bug, each one judged on its own target:
        `toy-1` (toy_parser, AFL-009), `tlv-2` (tlv_parser, AFL-010) and `mfp-1`
        (mini format parser, AFL-016). Shallow bugs are not covered.
      - **When evaluated.** On the first pilot only (or, after a restart, on
        the restarted first pilot, within the allowances left; Hang rule,
        *Restart from the first pilot*, human decision, 2026-11-14).
      - **Seeds.** The first pilot, the confirmation pilot and the main campaign
        each use fresh trial RNG seeds, pairwise disjoint: no seed is reused
        across any two of them. All seeds are recorded. The timing probe's
        fuzzer trials (baseline and official runs, seeds `base_seed + 2000 +
        i`) are a fourth set under the same rule (human decision, 2026-11-13;
        bullet "Probe conditions: baseline and two official runs"). After a
        restart, the restarted first pilot and the restarted confirmation
        pilot are a fifth and sixth set under the same rule (human decision,
        2026-11-14). The smoke run's trials (seeds `base_seed + 9000 + i`)
        are a seventh set under the same rule (lead decision, 2026-11-15).
        **Seed ranges (human decision, 2026-11-13).** This table is the one
        place to check the ranges. It clarifies the rule above without changing
        it; no pilot data exists yet.

        | Run | Seeds |
        |---|---|
        | Main campaign | `base_seed + i` |
        | First pilot | `base_seed + 1000 + i` |
        | Probe | `base_seed + 2000 + i` |
        | Confirmation pilot | `base_seed + 3000 + i` |
        | Smoke run (runner check only; max_execs 200; excluded from all analysis) | `base_seed + 9000 + i` |
        | Restarted first pilot | `base_seed + 4000 + i` |
        | Restarted confirmation pilot | `base_seed + 5000 + i` |

        The last two rows are used only after a restart (Hang rule, *Restart
        from the first pilot*; human decision, 2026-11-14).

        Every run kind has fewer than 1000 trials per (target, schedule) (AC
        "Runs ≥10 trials"), so no two ranges can meet, and the runner checks
        this directly at campaign start (AC "Seed sets disjoint, checked at
        campaign start").
      - **Trigger (two-sided, per deep bug).** (i) *Never found:* neither arm finds
        the bug in any first-pilot trial. (ii) *Trivially found:* both arms find
        the bug in every first-pilot trial within the first 5 % of
        `seconds_per_trial`. If either condition holds, that bug's target may be
        retuned.
      - **Limit.** A target is retuned at most once. This rule and the
        coverage-granularity fallback above are each evaluated exactly once, in
        total, on the first pilot (or, after a restart, on the restarted first
        pilot, within the allowances left; human decision, 2026-11-14), and
        each fires at most once over the whole project, restart included.
      - **After a retune.** Every AC of the target's ticket still passes. The
        change is logged in that target ticket's Log, with the first-pilot
        numbers that triggered it.
      - **Confirmation pilot.** If any target was retuned or the granularity
        changed, one confirmation pilot runs after all changes are applied, using
        the same pilot procedure except for its seeds, which are `base_seed +
        3000 + i`, not the first pilot's `base_seed + 1000 + i` (bullet "Seeds";
        human decision, 2026-11-13). Its results are recorded in
        `results/pilot/` and reported. It is never used to re-evaluate or
        re-trigger either rule, even when its numbers would meet a trigger. If
        nothing changed, no confirmation pilot runs.
      - **Freeze.** Before the main campaign, the targets and
        `experiments/configs/main.yaml` are frozen at a commit. Its hash is
        recorded in this ticket's Log and in each target ticket's Log (AFL-009,
        AFL-010, AFL-016). After the freeze, no target or threshold changes. The
        thresholds in this AC and in the granularity fallback cannot be edited
        once any pilot data exists.
      - **Pre-freeze check: depth sweeps on the frozen S0 (human decision,
        2026-11-12).** On the exact tree to be frozen (the candidate freeze
        commit, clean), `pytest -m slow` exits 0 and selects at least one S0
        single-byte substitution sweep for each experiment target (toy_parser,
        tlv_parser, mini format parser). This checks the measured bug-depth claims
        (shallow / deep against S0, PRD §8) on the frozen S0, including any S0
        changed by a retune. The sweeps are marked `@pytest.mark.slow` and
        excluded from the default run (`addopts` gets `-m "not slow"`), so the
        done-gate never runs them; this step is where they must pass. The freeze
        hash is not recorded until this passes on that commit. The Log's freeze
        entry records the command, its pass summary and the commit it ran on.
      - **Pre-run check: clean rebuild of the targets (human decision,
        2026-11-12).** `make -C targets clean all` is run, and exits 0, on the
        tree each run uses: before the first pilot, before the confirmation pilot
        (if one runs) and before the main campaign. On the candidate freeze
        commit it runs before the depth sweeps above, because they execute the
        binaries. Reason: `targets/bin/*` do not depend on the Makefile, so a
        compiler-flag change is not rebuilt by a plain `make -C targets`, and a
        run could use stale binaries (found by the AFL-009 reviewer). Each run's
        Log entry records the rebuild command, its exit status and the commit it
        ran on. `targets/bin/` is gitignored, so the rebuild does not dirty the
        tree.
      - **Pre-freeze check: timing probe (human decision, 2026-11-12).** After M1
        (PRD §10) and before the freeze, a timing probe runs one fuzzer trial per
        experiment target with nothing else running on the machine (no other
        trial, pilot or build). (Conditions changed, human decision, 2026-11-13:
        this one-trial-per-target probe is replaced by a concurrency-1 baseline,
        which is not used, and two official runs of six counted trials (plus
        fillers completing the last wave, human decision, 2026-11-13) at the
        campaign concurrency `c`; see bullet "Probe conditions: baseline and two official
        runs" under the checklist.) It measures each target's throughput in exec/s
        (final `execs` / final `elapsed_s` in `metrics.csv`) and toy_parser's hang
        rate (final `hangs` / final `execs`). toy_parser should never hang, so a
        nonzero hang rate means machine load is affecting timeouts. A nonzero
        rate is a reason to raise `--timeout` before the freeze, because timeouts
        are the one disclosed timing-dependent exception to exec-index replay
        (AFL-007 / ADR-0005). (Widened, human decision, 2026-11-13: a hang on
        any target, in any probe trial (counted or filler, baseline included,
        human decision, 2026-11-13), stops the freeze until the cause is
        found and the human decides; see "Hang rule" under the checklist's
        "Two probe runs; conservative value".) The freeze Log entry records each
        (target, schedule)'s exec/s and hang rate in both official probe runs,
        the `--timeout` value used, and the `--timeout` value frozen.
- [ ] **Pre-freeze checklist (human decision, 2026-11-12).** The freeze commit
      of the AC "Pre-registered target retuning rule and freeze" is not made, and
      its hash is not recorded, until every item below is ticked. Each item is
      ticked in this ticket's Log, with the date and the evidence named for it.
      This checklist gates only the freeze commit; it does not block implementing
      this ticket.
      - [ ] (a) AFL-015, AFL-018, AFL-027, AFL-028, AFL-030, AFL-031, AFL-036 and
        AFL-037 (AFL-030 added, human decision, 2026-11-14; AFL-031 added, lead
        decision, 2026-11-15; AFL-036 and AFL-037 added, lead decision,
        2026-11-16) are in `tickets/done/`.
        Evidence: `ls tickets/done/` output that lists all eight ticket files.
      - [ ] (b) `pytest -m slow` passes on every experiment target (toy_parser,
        tlv_parser, mini format parser): the bug-depth claims, measured against
        the S0s to be frozen. The conditions are those of the freeze AC's item
        "Pre-freeze check: depth sweeps on the frozen S0". Evidence: the command,
        its pass summary and the commit it ran on.
      - [ ] (c) The timing probe has run (the freeze AC's item "Pre-freeze check:
        timing probe", with the additions below), and PRD §8 (vii) states the
        measured executions per second of each target, replacing the estimate
        "roughly 20 executions per second". Evidence: the probe's numbers, the
        commit the probe ran on, and the commit that changed PRD §8 (vii).
      - [ ] (d) The lead has decided (CLAUDE.md §7 delegation) between parallel trials and a fork server.
        Evidence: the decision, its date and the probe numbers it was based on.
        **Decided from the baseline, re-decided at most once (human decision,
        2026-11-13; replaces the earlier reconciliation of baseline and official
        values).**
        - (d) and `c` (item (i)) are decided from the baseline's numbers,
          labelled "baseline: informs (d) and c, not used" (bullet "Probe
          conditions: baseline and two official runs"), before the first
          official run.
        - The decision record states the rule the decision used, e.g. "parallel
          at `c` because `c` × per-trial exec/s beats the fork-server estimate".
        - **Stated rule (lead decision, 2026-11-14).** Parallel trials, no fork
          server, `c` = 5. The one permitted revision is to `c` = 3, made if
          the first official run's per-trial exec/s falls below 80 % of the
          baseline's (the concurrency-1 baseline); otherwise `c` stays 5.
          Exactly 80 % keeps `c` = 5. No other revision of (d) or `c` is
          permitted. A repeated first official run at `c` = 3 is not revised
          again (at most one revision, below); its comparison is recorded
          (sub-bullet *If `c` = 3 is also below 80 %*).
          - *Comparison (lead decision, 2026-11-14).* Per target: the first
            official run's per-trial exec/s for a target is the lower exec/s
            of its two counted trials in that run (one per schedule; bullet
            "Two probe runs; conservative value"). It is compared with the
            baseline's exec/s for the same target, taken the same way (the
            lower of its two schedules). The revision is made if any campaign
            target is below 80 %.
          - *If `c` = 3 is also below 80 % (lead decision, 2026-11-14).* If
            the repeated first official run at `c` = 3 also falls below 80 %
            on any campaign target, `c` stays 3 and this is recorded in this
            ticket's Log. There is no second revision. The lower per-trial
            exec budget is disclosed as a threat to validity in PRD §8 (vii).
        - After the first official run, whether its values would have changed
          (d) or `c` is checked against that stated rule, not argued afresh.
          - If they do not change the decision under the stated rule, the
            record adds the official values and nothing is repeated.
          - If they do, (d) and `c` are revised, at most once and only before
            the first pilot (after a restart, only if the one revision was not
            already used, and only before the restarted first pilot; Hang rule,
            *Restart from the first pilot*, human decision, 2026-11-14). Any revision of (d) or `c` repeats the first
            official run (at the new `c`, if `c` changed), and `k` (item (h)) is
            fixed from the repeated run's crash durations (human decision,
            2026-11-13). The repeated run is then the first official run
            for every purpose; the values of the run it replaces are recorded,
            labelled "superseded: ran at c = ____, not used". "Not used"
            applies to exec/s, hangs and `k`, not to the `D_max` floor: the
            superseded run's `D_max` still counts towards item (h)'s floor
            (human decision, 2026-11-14).
          - A revision of (d) alone, with `c` unchanged, also repeats the first
            official run, because a fork server changes exec/s, crash timing
            and possibly hang behaviour. A fork server is its own ticket, and
            the first official run is repeated after that ticket lands (human
            decision, 2026-11-13). The stated rule above permits no revision
            of (d), so this case does not arise (lead decision, 2026-11-14).
        - Rationale: concurrency is exactly what the baseline cannot show, and
          the repeat is cheap because the first official run comes before the
          first pilot anyway.
        - The measured values the decision record states are the official
          runs' conservative values, never the baseline's (bullet "Two probe
          runs; conservative value").
      - [ ] (e) The working tree is clean and everything is pushed. "Clean" is
        this ticket's definition: `git status --porcelain --untracked-files=no`
        prints nothing. "Pushed": `git status -sb` shows the branch is not ahead
        of origin. The user runs the push (CLAUDE.md §7). Evidence: the output of
        both commands.
      - [ ] (f) Clean rebuild (human decision, 2026-11-12). `make -C targets clean
        all` runs, and exits 0, on the commit being frozen. It runs before (b)'s
        `pytest -m slow` and before the timing probe in (c), so every campaign
        binary is built with the frozen commit's flags. Reason: `targets/bin/*`
        do not depend on the Makefile, and the local tlv_parser and spike
        binaries predate the `-fno-omit-frame-pointer` change (AFL-009 review).
        This is the freeze-commit run of the freeze AC's item "Pre-run check:
        clean rebuild of the targets". Evidence: the command, its exit status
        and the commit it ran on.
      - [ ] (g) Prediction recorded before the pilot (human decision,
        2026-11-12). A calibration prediction for `toy-1` is written in this
        ticket's Log before any pilot trial runs. Evidence: the Log line's date
        is earlier than the date of the pilot's first trial (the earliest
        `started_at` in the `run.json` files under `results/pilot/`).
      - [ ] (h) Timeout set from the measured crash durations (human decision,
        2026-11-13). Reason: the executor ranks hang above crash (ADR-0005 §4),
        so a crash whose ASan report (mostly symbolization) runs past the
        timeout is recorded as `hang` and lost as a crash event. Under CPU load
        (20 `yes` processes) at the 1 s timeout, `test_asan_crash_despite_parent_env`
        failed 129 of 600 runs, and `test_toy1_deep`, `test_toy2_shallow` and
        `test_fixture_not_stale` also failed. A lost crash leaves a planted bug
        unrecorded and biases time-to-first-crash, possibly differently in the
        two arms. Rule (interpretation confirmed, human decision, 2026-11-13: the
        measurement runs twice, before the first pilot, which fixes `k`, and on
        the candidate freeze commit; a violation on the second run raises
        `timeout_s` with `k` unchanged, and a lower timeout the pilots ran under
        is recorded):
        - Before any pilot trial runs, a multiple `k` (> 1, the margin) is chosen
          from the numbers of the first run of the crash-duration measurement
          (bullet "Crash-duration measurement" below; the first official run,
          never the baseline, human decision, 2026-11-13; if (d) or `c` is
          revised under (d), the repeated first official run, human decision,
          2026-11-13). `k` is not changed once
          any pilot trial has run.
        - The campaign timeout `timeout_s` satisfies `timeout_s ≥ k × D_max`,
          where `D_max` is the slowest `wall_s` over all bugs in a run of the
          measurement. This holds for every run of the measurement, including
          the one on the candidate freeze commit. If a later run breaks it,
          `timeout_s` is raised (with `k` unchanged) before the freeze, and the
          value the pilots ran with is recorded.
        - `timeout_s` is the value of `timeout_s` in
          `experiments/configs/main.yaml` (AC "Campaign timeout and concurrency
          from the config"). It is the same number as the "`--timeout` value
          frozen" recorded by the freeze AC's item "Pre-freeze check: timing
          probe", not a second value. That item's reason to raise `--timeout`
          (a hang on any target, per the "Hang rule" in bullet "Two probe runs;
          conservative value") still applies on top of this floor.
        - Because the floor must hold for every run, `timeout_s ≥ k ×` the
          larger of the two runs' `D_max`: the longer crash duration always
          governs, whether or not the runs disagree (bullet "Two probe runs;
          conservative value" below, whose divergence check also applies to
          `D_max`).
        - Superseded runs count towards the floor (human decision,
          2026-11-14). "Every run" includes a first official run superseded
          under (d) and any official run superseded by a restart (Hang rule,
          *Restart from the first pilot*): `timeout_s ≥ k ×` the largest
          `D_max` over all official runs, superseded or not. The baseline's
          `D_max` stays outside the floor, as before (bullet "Which runs
          count"; confirmed, human decision, 2026-11-14: the floor protects
          against crashes lost as hangs under campaign load, and the baseline
          measures at `c` = 1 on an otherwise idle machine). Rationale for
          counting superseded runs: including
          them can only raise the timeout, and a longer timeout costs time
          only when hangs occur, which are expected to be zero; it also
          avoids choosing which runs count after seeing their numbers. `k`
          itself is still fixed only as stated above and is not refixed
          after a restart.
        - ADR-0005 §4 references this rule (human decision, 2026-11-13: note
          approved; the architect writes it in the ADR, not this ticket).
        - Evidence, to be filled in in the Log entry: `k` = ____; date `k` was
          chosen = ____ (earlier than the earliest `started_at` under
          `results/pilot/`); commit of the probe run `k` was chosen from = ____;
          `D_max` per probe run = ____ s (bug id ____, commit ____);
          largest superseded-run `D_max` = ____ s (bug id ____, commit ____,
          run ____; ____ if none) (human decision, 2026-11-14);
          `timeout_s` = ____ s; if raised after a pilot, the value the pilots
          used = ____ s.
      - [ ] (i) Concurrency within the physical cores (human decision,
        2026-11-13). The campaign concurrency `c` (the number of trials running
        at once; `concurrency` in `experiments/configs/main.yaml`; 1 when trials
        run sequentially) is at most the output of `sysctl -n hw.physicalcpu` on
        the campaign machine (physical cores, not `hw.logicalcpu`). The same `c`
        is the concurrency of the crash-duration measurement's official runs
        (the baseline's runs at 1), and it is
        consistent with the decision in (d). (Human decision, 2026-11-13:) `c`
        is chosen with (d), from the baseline's numbers, and is the concurrency
        of both official probe runs, for their fuzzer trials and their
        crash-duration measurement; the baseline runs at 1 (bullet "Probe
        conditions: baseline and two official runs"). The runner enforces the cap as a
        refusal at campaign start with no override flag (interpretation
        confirmed, human decision, 2026-11-13; AC "Campaign timeout and
        concurrency from the config"). The campaign machine is this Mac: macOS
        with Homebrew LLVM, and every probe, pilot and main-campaign run is on
        it (PRD §8 threats, the departure from NFR-4); its physical core count
        is the output of `sysctl -n hw.physicalcpu`. If `sysctl` fails, prints
        nothing, or prints something that is not a positive integer, the runner
        refuses to start; no such case skips the cap (same AC) (human decision,
        2026-11-13). (Lead decision, 2026-11-14: `c` = 5, or `c` = 3 after
        the one revision permitted by the stated rule in item (d).) Evidence:
        the `sysctl -n
        hw.physicalcpu` output = ____; chosen `c` = ____; date = ____.
      - [ ] (j) PRD §8 "Timing-dependent hangs" updated with the measured values
        and read by the human (human decision, 2026-11-13). The PRD is not
        edited before the measured numbers exist. After the timing probe's run
        on the candidate freeze commit, and once (h) and (i) are filled in, the
        entry is rewritten from the template below with the measured values
        filled in. The human then reads the changed text as pre-registration
        text, before the freeze commit. This is the PRD change the Log entry of
        2026-11-13 proposed. Evidence: the commit that changed PRD §8, and the
        date the human read the text (earlier than the freeze commit).
        Each hang blank in the template (toy_parser, tlv_parser, mini_format;
        run 1 / run 2) is that target's conservative value for that official
        run: the higher final `hangs` of its two schedules' counted trials,
        never a filler (2026-11-13; bullet "Two probe runs; conservative
        value"; counted trials, human decision, 2026-11-13).
        Template (every ____ is filled from the Log; nothing else changes
        without a human decision):

        > Timing-dependent hangs: whether an execution hangs depends on machine
        > load as well as on the input, and parallel trials make this worse; one
        > differing hang changes the later corpus in both arms, so exec-index
        > replay holds only up to the first differing timeout (ADR-0005 §4). The
        > executor ranks hang above crash, so a crash whose ASan report runs past
        > the timeout is recorded as a hang and lost as a crash event, which
        > biases time-to-first-crash. Mitigation, with the margin fixed before
        > any pilot: the campaign timeout is `timeout_s` = ____ s, at least
        > k = ____ (chosen ____, before the first pilot) times D_max, the slowest
        > crash duration of any planted bug's known trigger at the campaign
        > concurrency; D_max was ____ s (bug ____) before the first pilot and
        > ____ s (bug ____) on the freeze commit. [If raised after the pilots:
        > the pilots ran with ____ s.] At most c = ____ trials run at once, not
        > more than the campaign machine's ____ physical cores. Monitors: the
        > timing probe's final `hangs` on every target, expected 0 in both runs
        > (measured per target, run 1 / run 2: toy_parser ____ / ____,
        > tlv_parser ____ / ____, mini_format ____ / ____), and the
        > crash-duration measurement (AFL-011). *(Added 2026-11-12, human
        > decision; measured values filled in ____, under item (j), human
        > decision 2026-11-13.)*
      - [ ] (k) Planted-bug platform constraint holds for every campaign target
        at the freeze (lead decision, 2026-11-14; PRD §8 threats, the line
        after "Platform, a departure from NFR-4"). On the candidate freeze
        commit, every planted bug of every campaign target is reported by ASan
        with a stack whose `crash_site` is a target function; none is an
        integer divide by zero (on macOS/arm64 `sdiv` does not trap: it gives
        0 and the run exits clean); and every campaign target's source
        passes AFL-030's AC "Strict static source check", which holds the list
        of banned forms (kept there only, not copied here). Evidence: the
        crash-duration measurement's run on the candidate freeze commit passing
        its *Validity* rule (every row `outcome == "crash"`, signal 6,
        `crash_site` equal to the bug's `function`); AFL-030's static test's
        pytest pass summary on that commit; and, per campaign target, a review
        that no planted bug's path contains `/` or `%` arithmetic (as AFL-010's
        "Two planted bugs" AC requires), with the commit it was done on.
      - [ ] (l) The first pilot shows no `no_stack` crash on any target, or
        option B has been reconsidered and decided (AFL-030 pre-registered
        contingency; ADR-0003 "Pre-registered contingency") (lead decision,
        2026-11-15). The count is the number of rows with
        `crash_site == "no_stack"` in each pilot trial's own
        `crash_events.csv`, per target and per arm. The runner or the pilot
        evaluation step writes it; AFL-012 does not read pilot data. (l) is
        checked before the freeze.
      - **Timing-probe additions (human decision, 2026-11-12).** These extend the
        freeze AC's item "Pre-freeze check: timing probe"; that item's text is
        unchanged except as amended 2026-11-13 (see "Probe conditions: baseline
        and two official runs"). In addition to what that item measures, the probe reports, for
        each experiment target, from the final row of that trial's `metrics.csv`
        (AFL-007; per (target, schedule) trial of each run since the human
        decision of 2026-11-13, bullet "Probe conditions: baseline and two
        official runs"):
        - the final `hangs`;
        - the final `hang_time_s`: the sum of `exec_time` over the executions
          whose outcome is `"hang"`, including the kill and the AFL-028 stderr
          drain (`DRAIN_TIMEOUT_S`, at most 1 s per hang);
        - the hang overhead, `hang_time_s − hangs × timeout_s`, where
          `timeout_s` is the `--timeout` the probe ran with. This is the time
          each hang costs beyond the timeout itself (process start, kill, reap
          and drain), summed over hangs; when `hangs > 0` the probe also reports
          it divided by `hangs` (architect recommendation, 2026-11-12).

        The expected values for every target (widened from toy_parser only,
        2026-11-13, per the "Hang rule") are `hangs` 0, `hang_time_s` 0.0 and
        overhead 0.0. The freeze Log entry records these numbers with the ones
        the timing-probe item lists.
      - **Crash-duration measurement (human decision, 2026-11-13).** Part of the
        timing probe of item (c). It extends the freeze AC's item "Pre-freeze
        check: timing probe", whose text is unchanged except as amended
        2026-11-13; the exec/s and hang measurements above are unchanged by this
        bullet (their conditions were amended 2026-11-13; see "Probe
        conditions: baseline and two official runs"). Its numbers set `timeout_s` in (h).
        Interface confirmed as written below (`--crash-probe`, `R` rounds,
        `probe_timeout_s`, the `results/probe/<commit>/` paths and the
        validity rule; human decision, 2026-11-13).
        - *Command.* `python harness/run_campaign.py
          experiments/configs/main.yaml --crash-probe`. This mode runs no fuzzer
          trial and creates no trial directory.
        - *When and on what.* Once before the first pilot (its numbers fix `k`
          in (h)), and again on the candidate freeze commit, after (f)'s clean
          rebuild. Each run is on committed code with a clean tree (this
          ticket's definition), directly after `make -C targets clean all` exits
          0 on that commit, with nothing else running on the machine (no trial,
          pilot, build or test suite) besides the measurement's own processes.
          These two are the official runs. The baseline adds one more run of
          this measurement, at `c` = 1, before the first official run; it does
          not fix `k` and is not used (2026-11-13; see "Probe conditions:
          baseline and two official runs").
        - *What runs.* Every bug in `targets/ground_truth.json` whose `target`
          is a campaign target, with its trigger from `targets/triggers.json`
          (the table of the "Pre-flight symbolizer check"). Each run goes
          through `fuzzer.executor.Executor` against `targets/bin/<target>`, in
          the runner's own environment. `c` workers (item (i), the campaign's
          planned concurrency; 1 in the baseline, whatever `main.yaml` says,
          bullet "Probe conditions: baseline and two official runs") run in
          parallel; each runs every trigger once per
          round, for `R` rounds, so each bug gets `c × R` runs (`R` ≥ 1,
          recorded). The executor timeout for the measurement,
          `probe_timeout_s`, is chosen so that no run times out, and is
          recorded.
        - *What is recorded.* `results/probe/<commit>/crash_durations.csv`
          (`<commit>` = the full 40-character `git rev-parse HEAD`), one row per
          run, columns `bug_id`, `target`, `worker`, `round`, `concurrency`,
          `outcome`, `signal`, `wall_s`, `crash_site`. `wall_s` is the run's
          `ExecResult.exec_time`: monotonic wall time from process start until
          the process is reaped after SIGABRT, so it includes ASan's report and
          its symbolization. Also `results/probe/<commit>/crash_durations.json`
          with `commit`, `concurrency`, `R`, `probe_timeout_s`, the `sysctl -n
          hw.physicalcpu` value, per bug the run count and the median and
          maximum `wall_s`, and `D_max` (the maximum `wall_s` over all rows)
          with its bug id.
        - *Validity.* Every row has `outcome == "crash"`, `signal` 6 (SIGABRT)
          and `crash_site` equal to the bug's `function` in `ground_truth.json`.
          Otherwise the mode exits non-zero naming the bug and the row, and
          writes no `D_max`: a timed-out run's duration is censored, so `D_max`
          is unknown. The measurement is then re-run with a higher
          `probe_timeout_s`, or the symbolizer problem is fixed first.
        - *Log.* Each run's Log entry records the commit, the rebuild's exit
          status, `c`, `R`, `probe_timeout_s`, each bug's median and maximum
          `wall_s`, and `D_max` with its bug id. The freeze Log entry also
          records the numbers of the run on the candidate freeze commit, with
          the timing-probe numbers above.
        - *Tests.* With the executor stubbed (a fixed `exec_time` per bug):
          (a) the CSV has `c × R` rows per bug with exactly the columns above,
          and the JSON's `D_max` equals the largest `wall_s` and names its bug;
          (b) one stubbed timed-out run makes the mode exit non-zero, naming
          that bug, with no `D_max` in any output; (c) no trial directory is
          created in either case.
      - **Probe conditions: baseline and two official runs (human decision,
        2026-11-13).** Replaces the one-trial-per-target, nothing-else-running
        conditions of the freeze AC's item "Pre-freeze check: timing probe" for
        the exec/s and hang measurements.
        - *Baseline.* One measurement at concurrency 1, before the first
          official run: the six counted fuzzer trials described under
          *Official runs*, one per (target × schedule), run one at a time
          (`c` = 1: six waves of 1, no fillers), about one hour at 600 s each
          (human decision, 2026-11-13), and the crash-duration measurement with `c` = 1
          (the runner's baseline mode runs every trial, and the crash-duration
          measurement, at `c` = 1 whatever `main.yaml` says; lead decision,
          2026-11-15). It
          runs under the same conditions as the official runs: committed code
          with a clean tree (this ticket's definition), directly after `make -C
          targets clean all` exits 0 on that commit, with nothing else running
          on the machine. Wherever its values are recorded they are labelled
          "baseline: informs (d) and c, not used". They inform the decision in
          (d) and the choice of `c` in (i), and are never a used value (bullet
          "Two probe runs; conservative value"). The divergence check does not
          apply to the baseline. The hang rule does (human decision,
          2026-11-13; replaces "the divergence check and the hang rule do not
          apply to the baseline").
        - *Official runs.* Two, at the points of "When and on what" above
          (before the first pilot, and on the candidate freeze commit), under
          the same conditions. Each launches one fuzzer trial per (target ×
          schedule), six in all, running `c` at a time (item (i)), in a launch
          order that alternates the arms (UNIFORM, FAST, UNIFORM, …), and runs
          the crash-duration measurement at the same `c`. Exec/s, final `hangs`
          and the "Timing-probe additions" are recorded per (target, schedule).
          These six are the run's counted trials; see *Waves and fillers*
          below (human decision, 2026-11-13). This applies to both official
          runs, including a repeated first official run under (d).
        - *Waves and fillers (human decision, 2026-11-13; replaces the
          ⌈c/6⌉-replica rule).* Every probe run is made of full waves of
          exactly `c` trials: its `n` counted trials, one per (target ×
          schedule) (`n` = 6 with three targets, 4 with two), and filler
          trials that make up the rest of the last wave (`c` × ⌈`n`/`c`⌉ −
          `n` fillers). Every counted trial therefore runs at
          full load by construction. Fillers are real fuzzing trials of the
          campaign targets, interleaved in the same round-robin launch order
          (the `n` (target, schedule) pairs, arms alternating, counted trials
          first, then fillers continuing the same cycle), so the load they add
          looks like the campaign's. They are recorded as "filler, not used",
          excluded from every exec/s and `D_max` value, and covered by the hang
          rule. The table shows only the cases that can occur: the baseline,
          and the official runs at `c` = 5 or 3 (item (d); lead decision,
          2026-11-15).

          | Run | Targets | Trials |
          |---|---|---|
          | Baseline (labelled not used) | 3 | 6 sequential |
          | Baseline (labelled not used) | 2 | 4 sequential |
          | Official, c = 5 | 3 | 5 + 5: 6 counted, 4 fillers |
          | Official, c = 5 | 2 | 5: 4 counted, 1 filler |
          | Official, c = 3 | 3 | 3 + 3: 6 counted, no fillers |
          | Official, c = 3 | 2 | 3 + 3: 4 counted, 2 fillers |

          *Two targets (lead decision, 2026-11-14; AC "≥3 targets (PRD §8)",
          bullet "AFL-016 cutoff").* The seed ranges stay as they are (bullet
          "Seeds"). The primary family shrinks to m = 4, by AFL-012's existing rule (technical
          notes, "Primary family"). Each pilot has 12 trials and the main
          campaign 40.

          Rationale: replication is not what makes the probe reliable. The
          repeated measurement is the baseline plus the two official runs on
          the same seeds, with the official runs checked by the 20 %
          divergence check; the probe's job is calibration (timeout, exec/s),
          not a statistical test. How trials are launched (waves or a rolling
          pool) is the architect's choice; fillers keep every counted trial at full
          load either way.
        - *Trial length and seeds (human decision, 2026-11-13).* Every probe
          trial, baseline and official, runs the campaign's `seconds_per_trial`
          from `main.yaml`, so exec/s and hangs are measured over the same
          window as a campaign trial. Probe trial `i` uses the RNG seed
          `base_seed + 2000 + i`, a reserved range of its own. Definition of
          `i` (human decision, 2026-11-13; replaces "the trial's replica number
          within its (target, schedule)"): `i` is counted within the trial's
          (target, schedule). Let `i₀` be the first index the main campaign's
          `base_seed + i` uses (0 or 1). The counted trial of each (target,
          schedule) has `i = i₀`; that pair's fillers take `i₀ + 1`, `i₀ + 2`,
          … in round-robin launch order. So no filler shares a (target,
          schedule, seed) with a counted trial, and at the same `c` every run
          gives its fillers the same seeds. Every probe run (the baseline, the
          first official run and any repeat of it, and the second official
          run) uses these same seeds (human decision, 2026-11-13). Rationale:
          run 1 against run 2, and the baseline against both, then compare the
          same trajectories, so any difference comes from load or code, not
          from seed variance, and that is what the divergence check detects.
          The probe is one of the
          pairwise-disjoint seed sets of the freeze AC's "Seeds" bullet. All
          probe seeds are recorded in each run's Log entry. Rationale:
          `timeout_s` is set from the probe's trials, so the campaign must not
          re-run the probe's trajectories, and a small `base_seed` must not
          cause collisions. The crash-duration measurement runs fixed triggers
          and uses no RNG, so seeds do not apply to it.
        - *Order.* (1) the baseline; (2) the decision in (d) and `c` in (i),
          both from the baseline's numbers; `main.yaml` holds the campaign's
          `c` (5) as `concurrency` from stop 2 onwards, and a commit is needed
          only if item (d)'s one permitted revision to `c` = 3 happens, landing
          before the repeated first official run (lead decision, 2026-11-15); (3) the first official run, at that `c`, whose crash
          durations fix `k` (item (h)); (4) the first pilot; (5) the second
          official run, on the candidate freeze commit. (Amended, human
          decision, 2026-11-13: between (3) and (4), the first official run's
          values are checked against the rule (d)'s record states; if they
          change (d) or `c`, the decision is revised once, and any revision of
          (d) or `c` repeats the first official run (at the new `c` if `c`
          changed; after the fork-server ticket lands if (d) changed) and `k`
          is fixed from the repeated run instead (item (d); human decision,
          2026-11-13). Nothing is revised after the first pilot starts,
          except under the Hang rule's *Restart from the first pilot*, where an
          unused revision may be made before the restarted first pilot (human
          decision, 2026-11-14).) (Lead decision, 2026-11-14: step (2) records
          parallel trials, no fork server and `c` = 5; the check between (3)
          and (4) is item (d)'s stated rule: if the first official run's
          per-trial exec/s is below 80 % of the baseline's, `c` is revised to
          3 and the first official run is repeated at `c` = 3, with `k` fixed
          from the repeat; otherwise `c` stays 5. No fork-server repeat
          arises.)
        - *Which runs count.* Wherever this ticket speaks of the probe's two
          runs, its first or second run, either run or every run (items (c),
          (h), (i) and (j), and the bullets "Crash-duration measurement" and
          "Two probe runs; conservative value"), it means the two official runs.
          The baseline is none of them. One exception: the "Hang rule" covers
          every probe trial, the baseline's included (human decision,
          2026-11-13).
      - **Two probe runs; conservative value (human decision, 2026-11-13).**
        The timing probe, meaning the exec/s and hang measurements, the
        "Timing-probe additions" and the crash-duration measurement, runs at the
        two points of "When and on what" above: before the first pilot and on
        the candidate freeze commit. The whole probe runs both times, not only
        the crash-duration part (human decision, 2026-11-13).
        - Both runs' values are recorded: each run gets its own Log entry, and
          the freeze Log entry repeats the numbers of both runs side by side,
          as a table with one row per probe trial of each official run, fillers
          included (human decision, 2026-11-13; replaces "one row per (target,
          schedule)"), giving the trial's run, target, schedule, seed, wave,
          "counted" or "filler, not used", exec/s, final `execs`, final
          `hangs`, hang rate (final `hangs` / final `execs`), `hang_time_s` and
          hang overhead, plus each official run's `D_max` with its bug id (human
          decision, 2026-11-13). The baseline's numbers are given in a separate
          table with the same columns, labelled "baseline: informs (d) and c,
          not used". (There is no replica column; bullet "Probe conditions:
          baseline and two official runs", *Waves and fillers*.)
        - The conservative value is always used, per target, whether or not the
          runs disagree (human decision, 2026-11-13; replaces the earlier "if
          the two runs disagree substantially"): over the target's two schedules
          and both official runs (counted trials only; filler rows never supply
          a used value, human decision, 2026-11-13), the lower exec/s and the higher hang count
          (human decision, 2026-11-13), and the larger `D_max` (which sets
          `timeout_s` through `k`, item (h)). "Used" means the value given in
          PRD §8 (vii) (item (c)), the measured values (d)'s decision record
          states, and the value written into item (j)'s template; these are
          always the official, concurrent values, never the baseline's (human
          decision, 2026-11-13).
        - For crash duration this needs no threshold: item (h)'s floor must hold
          for every run, so the larger `D_max` always governs `timeout_s`;
          superseded official runs count towards that floor too (item (h),
          bullet "Superseded runs count towards the floor"; human decision,
          2026-11-14).
        - **"Substantially" for exec/s: RESOLVED (human decision, 2026-11-13).**
          No tolerance: the lower exec/s is always used (bullet above). The
          earlier proposal (any difference, or lower < 90 % of higher) is kept
          in the Log.
        - **Divergence check (human decision, 2026-11-13).** For each (target,
          schedule)'s exec/s and for `D_max` (not hang rate: see "Hang rule" below), with `a` and `b` the two
          official runs' values (the baseline is outside this check), the relative difference is `|a − b| / max(a, b)` (0 when
          `a = b = 0`). If it is `> 0.20` for any of them, the probe result is
          not trusted: no value of either run is used (as defined above) and
          `timeout_s` is not frozen until the cause is investigated (e.g. the
          machine was not idle, or the measurement is unstable) and the human
          decides. The cause and the decision are recorded in the Log. `k` stays
          as item (h) fixed it. Examples: exec/s 100 and 79 gives 0.21, fails;
          100 and 80 gives 0.20, passes (not `> 0.20`).
          - **Hang rule (human decision, 2026-11-13; replaces the proposed
            hang-rate floor; scope widened, human decision, 2026-11-13).** Any
            hang (final `hangs` > 0) in any probe trial, on any target and
            either schedule, counted or filler, in the baseline or in either
            official run (including a repeated first official run), means the
            probe values are not used and
            `timeout_s` is not frozen until the cause is investigated and the
            human decides. Reason: no planted target should hang (toy_parser
            and tlv_parser have no input-dependent loops; mini_format's record
            loop is bounded by the input length), so the expected rate is
            exactly 0, and a floor would hide a slow ASan report recorded as a
            hang or a timeout too short for the load. A hang in the baseline,
            at `c` = 1, is even more telling, because it points to a target
            bug rather than to load (human decision, 2026-11-13).
            - "Investigate" means finding the cause. Load or a slow crash
              report: raise `--timeout` and rerun the probe as *What is rerun*
              below states (human decision, 2026-11-14; replaces "run the
              whole probe again (both runs)"). A target that genuinely hangs: a target bug, fixed before
              the freeze. Either way the human decides before any value is
              used, and the cause and the decision are recorded in the Log.
            - *What is rerun (human decision, 2026-11-13).* By default, after a
              `--timeout` raise only the two official runs are rerun, not the
              baseline: a higher `--timeout` changes what a hang costs, not
              what (d) and `c` were based on. Two exceptions:
              - (a) The hang was in the baseline itself: the baseline is rerun
                as well. A hang at `c` = 1 is not a load effect, and the rerun
                has to show it is gone under the same conditions in which it
                appeared.
              - (b) The cause was a target bug that was then fixed: the depth
                sweeps (freeze AC item "Pre-freeze check: depth sweeps on the
                frozen S0", checklist item (b)), the baseline and both official
                runs are all rerun. The target's code changed, so the
                baseline's exec/s, and the (d) and `c` decision built on them,
                describe a binary that no longer exists. If the rerun baseline
                would change (d) or `c` under the decision rule (d)'s record
                states, the existing rule applies: at most one revision, and
                only before the first pilot (item (d)). If the bug is fixed
                after the first pilot has started (e.g. found from a hang in
                the second official run on the candidate freeze commit), the
                next sub-bullet, *Restart from the first pilot*, governs
                (human decision, 2026-11-14).
            - *Restart from the first pilot (human decision, 2026-11-14).* A
              target bug fixed after the first pilot has started restarts the
              pre-freeze sequence once, from the first pilot: the depth
              sweeps, the baseline and both official runs are rerun as in
              exception (b) above. Order (confirmed, human decision,
              2026-11-14): fix → depth sweeps for the fixed target → baseline
              → first official run → restarted first pilot → (any retune and
              restarted confirmation pilot) → depth sweeps and second official
              run on the candidate freeze commit. The fixed target's depth
              sweeps thus run twice, straight after the fix and on the
              candidate freeze commit (bullet "Minimal fix"). Safeguards:
              - **Trigger.** A demonstrated target bug only: a reproducer
                input that hangs at `c` = 1 with a generous timeout, which
                rules out machine load. The reproducer is committed and
                logged in this ticket's Log.
              - **Minimal fix.** The fix only removes the non-termination.
                Every AC of the target's ticket still passes, including the
                depth sweeps on that target's S0. Those depth sweeps run
                straight after the fix, before the restarted baseline, and
                must pass there (human decision, 2026-11-14). Rationale: a fix
                that changed a bug's depth would otherwise be caught only on
                the candidate freeze commit, after the restarted first pilot
                had already run on it. The fix is logged in the target
                ticket's Log (AFL-009, AFL-010 or AFL-016).
              - **At most once.** One restart for the whole project. A second
                late target bug cannot trigger another; it takes the
                exclusion route (last bullet).
              - **Fresh seeds.** The restarted first pilot uses `base_seed +
                4000 + i` and the restarted confirmation pilot uses
                `base_seed + 5000 + i` (bullet "Seeds" table). The probe keeps
                its `base_seed + 2000 + i` seeds (bullet "Probe conditions:
                baseline and two official runs").
              - **Allowances already used stay used.** This prevents
                re-rolling the pilot. A target already retuned cannot be
                retuned again. If the granularity fallback already fired, the
                experiment stays on hit counts. If the one revision of (d) or
                `c` (item (d)) was already used, there is no second; if it was
                not, it is available only before the restarted first pilot.
                `k` stays as item (h) fixed it, because it is not changed once
                any pilot trial has run (confirmed, human decision,
                2026-11-14): `k` is a margin, not a duration. Item (h)'s floor
                `timeout_s ≥ k × D_max` must still hold for every run of the
                crash-duration measurement, the rerun first official run on
                the fixed binary included; if the fixed binary's crashes are
                slower, `timeout_s` is raised and `k` stays the same, as for
                any later run that breaks the floor (item (h)). The restarted
                first pilot evaluates the triggers (retuning rule and
                granularity fallback) only within the allowances left. A
                restarted confirmation pilot runs only after a retune or a
                granularity change made on the restarted first pilot's results
                (the confirmation pilot's own condition); the fix itself needs
                no confirmation pilot, because the restarted first pilot
                already runs on the fixed binary (confirmed, human decision,
                2026-11-14).
              - **Nothing is discarded.** The original pilot data (first pilot
                and any confirmation pilot) is kept, not overwritten,
                labelled "superseded by restart", and reported in the
                write-up with the reason for the restart. Where it is kept is
                the architect's choice, but it must be under `results/`
                (gitignored), so keeping it cannot dirty the tree (human
                decision, 2026-11-14). The `D_max` values of official runs
                superseded by the restart still count towards item (h)'s
                floor (item (h)).
              - **No time to restart before the freeze deadline.** The
                affected target is excluded instead, with the existing
                `--allow-fewer-targets "<reason>"` override (AC "≥3 targets
                (PRD §8)"). The primary family then loses that target's two
                members, as AFL-012 specifies (technical notes, "Primary
                family": "its two members are then removed, m shrinks
                accordingly"), and the report discloses the exclusion. This
                avoids a late fix entirely.
              - **Rationale.** This is the only option in which the pilots,
                the retuning decision and (d) and `c` all describe the binary
                that is actually frozen. The safeguards keep a restart from
                becoming a second draw of pilot results. The case is unlikely:
                toy_parser and tlv_parser have no input-dependent loops, and
                mini_format's record loop is bounded by the input length.
            - The higher hang count, over both schedules and both official
              runs (counted trials only; filler rows never supply a used
              value, human decision, 2026-11-13), is still the one recorded as
              used (bullet above).
          - *Check (tester).* From the freeze Log table, the tester recomputes
            the relative differences for each (target, schedule)'s exec/s and
            for `D_max` across the two official runs and confirms that none is
            `> 0.20`, confirms that final `hangs` is 0 in every row of both
            tables, i.e. every probe trial, counted or filler, baseline
            included (human decision, 2026-11-13) (or, for either check, that
            the human's decision is logged), and that each used value is, per
            target, the conservative one over its two schedules and both
            official runs (counted trials only; filler rows never supply a
            used value, human decision, 2026-11-13).
            The tester also confirms that the baseline's numbers
            appear only in their own table, labelled "baseline: informs (d) and
            c, not used", and in the evidence of (d) and (i), never as a used
            value (human decision, 2026-11-13).
- [x] **Campaign timeout and concurrency from the config (human decision,
      2026-11-13).** `experiments/configs/main.yaml` has two required keys:
      `timeout_s` (float > 0) and `concurrency` (int ≥ 1). Their values are set
      by the "Pre-freeze checklist" items (h) and (i) and are frozen with
      `main.yaml`.
      - The runner passes `timeout_s` to every trial's CLI as `--timeout`
        (first pilot, confirmation pilot and main campaign; both arms). It
        never relies on the CLI's default of 1.0. The "Pre-flight symbolizer
        check" runs its triggers with the same `timeout_s`.
      - The runner runs at most `concurrency` trials at once.
      - Before any trial, the runner exits non-zero and creates no trial
        directories if either key is missing or invalid (message names the
        key), or if `concurrency` exceeds the output of `sysctl -n
        hw.physicalcpu` (message names both numbers). There is no override
        flag: no option, environment variable or config key skips or raises
        the cap, the same as the other pre-registration guards (S0 hash,
        symbolizer, clean tree). `concurrency` is a required key, enforced as
        a refusal at campaign start (human decision, 2026-11-13:
        interpretation confirmed).
      - **Unusable `sysctl` (human decision, 2026-11-13).** Before any trial,
        the runner also exits non-zero and creates no trial directories if
        `sysctl -n hw.physicalcpu` cannot give the cap: (1) it fails (exits
        non-zero, or the `sysctl` command is not found); (2) it prints nothing;
        (3) its output, stripped of surrounding whitespace, is not a positive
        integer (e.g. `0`, `-4`, `4.5`, `four`). The message names the command
        and what it returned. None of these cases skips the cap or falls back
        to a default core count.
      - The campaign metadata records `timeout_s`, `concurrency` and the
        `hw.physicalcpu` value.
      - Tests: (a) every trial's `run.json` `config` has `timeout_s` equal to
        `main.yaml`'s; (b) with `sysctl` stubbed to return 2, `concurrency: 3`
        exits non-zero with no trial directories, and `concurrency: 2`
        proceeds; (c) a config without `timeout_s`, and one without
        `concurrency`, each exit non-zero with no trial directories; (d) a
        grep check finds no option in `harness/run_campaign.py` that skips or
        raises the concurrency cap; (e) with `sysctl` stubbed, for each of the
        three cases above (exit status 1, and separately a missing command;
        empty output; output `0`, and separately `abc`), the runner exits
        non-zero, the message names `sysctl -n hw.physicalcpu`, and zero trial
        directories exist, with `concurrency: 1` so that only the `sysctl`
        result can cause the refusal (human decision, 2026-11-13).
- [x] **Campaign machine recorded (human decision, 2026-11-13).** The campaign
      machine is this Mac (macOS, Homebrew LLVM; PRD §8 threats, the departure
      from NFR-4). The campaign metadata of every run (first pilot,
      confirmation pilot, main campaign) records the machine: `model` (output of
      `sysctl -n hw.model`), `macos_version` (output of `sw_vers
      -productVersion`), `clang_version` (first line of `<CC> --version`, where
      `<CC>` is the compiler `targets/Makefile` builds with: Homebrew LLVM's
      `/opt/homebrew/opt/llvm/bin/clang` when present, ADR-0001) and
      `hw_physicalcpu` (the same `sysctl -n hw.physicalcpu` value the cap uses,
      not a second call's result). Test: with the four commands stubbed to fixed
      outputs, a short pilot's campaign metadata holds exactly those four
      values under those four keys.
- [x] **≥3 targets (PRD §8).** `experiments/configs/main.yaml` lists ≥3 distinct
      targets: toy_parser, tlv_parser and the AFL-016 mini format parser. Before
      starting any trial (main or pilot), the runner checks the config's distinct
      target count and that every target binary exists. If there are fewer than 3,
      it **refuses**: it exits non-zero with a message naming PRD §8 and runs no
      trial. Refuse, not just warn, because PRD §8 sets "≥3" as a design parameter
      of the main experiment. The only override is an explicit
      `--allow-fewer-targets "<reason>"`, matching the mitigation PRD §11 allows
      ("fewer targets" when CPU/time is short). When used, the override and its
      reason are written to the campaign metadata, so the report must disclose them
      as a threat to validity. Test: a 2-target config exits non-zero with no trial
      directories created. The same config with the override runs and records the
      reason.
      - **AFL-016 cutoff (lead decision, 2026-11-14; definition revised, lead
        decision, 2026-11-15).** The cutoff tests whether AFL-016 (mini format
        parser) is ready, not when its commit is made: AFL-016 must be in
        `tickets/done/`, closed by the crew-lead, by 2026-11-16, 12:00 Eastern
        Time. Its commit lands in the next stop. If AFL-016 closes on time but
        the commit is made later, the baseline (bullet "Probe conditions:
        baseline and two official runs") waits for the commit, because the
        probe cannot run on uncommitted code. A late commit never disqualifies
        AFL-016. If AFL-016 is not closed by then, the whole sequence
        (baseline, official runs, pilots and main campaign) runs on two targets: `main.yaml` lists
        toy_parser and tlv_parser, the runner is invoked with
        `--allow-fewer-targets "AFL-016 not ready by the pre-registered
        cutoff"`, and the report discloses the exclusion. AFL-016 cannot be
        added afterwards: the Hang rule's *Restart from the first pilot*
        covers fixes to target bugs, not adding a target. As for any excluded
        target (Hang rule, "No time to restart before the freeze deadline"),
        the primary family loses that target's two members (AFL-012).
        Wherever this ticket names the mini format parser, `mfp-1` or `mfp-2`
        as a campaign target or bug, that entry then drops out. The
        frontmatter's `depends_on` still lists AFL-016; under this cutoff it
        binds only until the baseline starts, after which this ticket
        proceeds without it.
- [x] **Initial corpus = S0 (human decision, 2026-11-07; PRD §8).** In
      `experiments/configs/main.yaml`, each target's initial corpus is exactly the
      directory `targets/seeds/<target>/` (`<target>` = binary name), which
      contains only `S0` (AFL-009/010/016). It is passed to every trial via the
      CLI's `--seeds DIR` (AFL-008) and is identical in both arms. The runner
      records the seed directory path and the SHA-256 of each seed file in it
      (non-hidden regular files, AFL-007 AC "Seed files and load order"; i.e. S0)
      in the campaign metadata. Test: the recorded corpus is the same for every UNIFORM
      and FAST trial of a target.
- [x] **Pre-flight S0 integrity check (human decision, 2026-11-07).** Before any
      trial of any run (first pilot, confirmation pilot or main campaign), the
      runner computes the SHA-256 of each target's `targets/seeds/<target>/S0` and
      compares it with that target's line in `targets/seeds/SHA256SUMS`
      (`sha256sum` output, `<hex>  <target>/S0`, committed with `S0` by
      AFL-009/010/016). That file is the single expected-hash record. The Freeze
      commit of the AC "Pre-registered target retuning rule and freeze" is what
      fixes it for the main campaign. A retune that changes `S0` updates
      `SHA256SUMS` in the same change and is logged as that AC requires. If any
      `S0` is missing or unreadable, `SHA256SUMS` or the target's line in it is
      missing, or the hashes differ, the runner aborts with an error naming the
      target and both hashes (or what is missing), and runs zero trials. There is
      no override flag (unlike `--allow-fewer-targets`): a mismatch always aborts.
      The verified hashes are the per-file SHA-256 values that the "Initial corpus
      = S0" AC records in the campaign metadata, not a second copy. Test: a missing
      `S0`, a tampered `S0` (one byte changed) and a missing `SHA256SUMS` entry
      each exit non-zero with no trial directories created; matching hashes
      proceed.
      - **Zero-length S0 (folded in from AFL-019, human decision, 2026-11-07).**
        The pre-flight also rejects any `targets/seeds/<target>/S0` of length 0.
        The runner exits non-zero with an error that names the target and says the
        seed file is empty, and creates no trial directories. This applies to the
        first pilot, the confirmation pilot and the main campaign, with no override
        flag. Rationale: `mutator.mutate(b"")` can return `b""`; every corpus seed
        descends from S0 and no operator empties a non-empty input, so a non-empty
        S0 makes `mutate(b"")` unreachable in a campaign.
      - Test: a config whose target has a zero-length `S0` (with a matching
        `SHA256SUMS` line, so only the length check can fail) exits non-zero, the
        error message names the target, and zero trial directories exist.
      - **Seeds dir holds only S0 (human decision, 2026-11-12; ADR-0005 §1).** The
        pre-flight also requires that, for each target, the set of non-hidden
        files in `targets/seeds/<target>/` (computed with AFL-007's seed-file
        function, the one `run(cfg)` loads from: regular files whose names do not
        start with `.`) is exactly `{S0}`. Otherwise the runner aborts before any
        trial (first pilot, confirmation pilot or main campaign), exits non-zero
        with an error naming the target and the unexpected files, and creates no
        trial directories. There is no override flag. Hidden files (e.g. Finder's
        `.DS_Store`) are ignored here because the loader never loads them. Tests:
        (a) adding a `.DS_Store` to a target's seeds dir still passes the
        pre-flight, and that target's trial `run.json` `seed_files` lists only
        `S0`; (b) adding a stray `S1` aborts with a message naming the target and
        `S1`, and zero trial directories exist.
      - `src/fuzzer/mutator.py` is unchanged by this check (`git diff` on it is
        empty).
      - The statement "non-empty S0 + no operator empties a non-empty input ⇒
        `mutate(b"")` is unreachable in a campaign" is recorded in a code comment
        next to the length check, citing AFL-011 (and AFL-019 as its origin).
- [ ] **Pre-flight symbolizer check (added 2026-11-12, human decision).** Origin:
      the "Symbolizer check" item in ADR-0005's "Open questions for the human"
      (`docs/adr/0005-stopping-and-exec-index-replay.md`). Reason: if ASan
      symbolization fails, `crash_site()` labels every crash `"no_target_frame"`
      (ADR-0005 §3) with no error, so de-duplication (AFL-013) and per-bug
      time-to-first-crash degrade silently, in both arms.
      - **Scope (revised 2026-11-12, human decision: supersedes toy-2-only).**
        One known-crashing trigger per planted bug, for every bug in
        `targets/ground_truth.json` whose `target` is a target of the campaign's
        config: `toy-1` and `toy-2` (toy_parser, AFL-009), `tlv-1` and `tlv-2`
        (AFL-010), `mfp-1` and `mfp-2` (AFL-016). That is every deep bug
        (`toy-1`, `tlv-2`, `mfp-1`) and every shallow one. This adopts the
        architect's recommendation in ADR-0005's "Open questions for the human"
        (item "Symbolizer check"). One input per bug; no depth sweep. The bullets
        "Trigger table", "What it does", "Pass condition", "Missing trigger
        aborts", "Otherwise abort" and "Tests", and the word "binaries" in "No
        override", are revised with it.
      - **Trigger table (revised 2026-11-12, human decision).** The known
        triggers live in one file, `targets/triggers.json`, next to
        `targets/ground_truth.json`. The runner reads them only from there, and
        target tests that check a trigger read the same file. `ground_truth.json`
        gets no trigger field. Format: one JSON object; each key is a bug id of
        `ground_truth.json`, each value is that bug's trigger bytes as a lowercase
        hex string, one input per bug. The toy_parser entries are
        `"toy-1": "42554761"` (`b"BUGa"`) and `"toy-2": "21616161"` (`b"!aaa"`);
        this ticket adds them if they are not already present. AFL-010 and AFL-016
        add the entries for their bugs (each has an AC for it); whichever of these
        tickets lands first creates the file in this format. The file is under
        `targets/`, so the freeze diff check ("Clean-tree provenance" (c)) covers
        it.
      - **What it does.** Part of the runner's pre-flight, run automatically at
        the start of every campaign (first pilot, confirmation pilot and main
        campaign), before any trial, in the runner's own process environment
        (the one the trials inherit), against the binaries the trials will use
        (`targets/bin/<target>`, after the freeze AC's item "Pre-run check: clean
        rebuild of the targets"). For each bug in scope, it reads the bug's entry
        in `targets/triggers.json`, runs that input once through
        `fuzzer.executor.Executor` against `targets/bin/<target>` (`<target>` =
        the bug's `target` in `ground_truth.json`), and calls AFL-007's shared
        `crash_site(stderr, source)` (`src/fuzzer/fuzzer.py`) on the result, with
        `source` = the bug's `file` in `ground_truth.json`. The runner has no
        crash-site or frame parsing of its own.
      - **Pass condition.** For every bug in scope, the result equals that bug's
        `function` in `targets/ground_truth.json`, read from that file, not
        hard-coded (today `"check"` for `toy-1`, `"scan"` for `toy-2`).
      - **Missing trigger aborts.** If `targets/triggers.json` is missing, or a
        bug in scope has no entry in it, or an entry is not valid hex, the runner
        aborts before running any trigger: it exits non-zero with zero trials run
        and no trial directories created, and the error names the bug id (or the
        missing file) and `targets/triggers.json`. So a new target's bugs cannot
        slip past the check.
      - **Otherwise abort.** If any one bug's result is any other value (a
        sentinel such as `"no_target_frame"`, `"unsymbolized"` or `"no_stack"`,
        or another function), the campaign aborts, even when every other bug
        passes: the runner exits non-zero with zero trials run and no trial
        directories created. The error message says ASan symbolization is not
        working (e.g. `llvm-symbolizer` missing or failing, or the target built
        without `-g`), and names, for each failing bug, the bug id, the input,
        the expected site and the value returned.
      - **No override.** There is no flag to skip or weaken this check (same
        reasoning as the S0 hash check). It is not a one-off checklist item and
        is not replaced by "Pre-freeze checklist" item (b): that runs once, on
        the freeze commit, under pytest's environment, while this check runs at
        the start of every campaign, in the runner's own environment, on the
        binaries the trials will use.
      - **Tests.** (a) With the real `targets/bin/*` binaries, the pre-flight
        runs one check per bug in scope, each `crash_site()` equals that bug's
        `function`, and the campaign proceeds; the test asserts that every bug
        of the config's targets in `ground_truth.json` was checked. (b) With
        `crash_site` (or the executor) stubbed so that a single bug (e.g.
        `toy-1`) yields `"no_target_frame"` while every other bug passes, the
        runner exits non-zero, the error message names the symbolizer problem
        and that bug, and zero trial directories exist; the same holds in pilot
        and in main-campaign mode. (c) With a test copy of `ground_truth.json`
        holding a bug that has no entry in the trigger table, the runner exits
        non-zero, the error names that bug and `targets/triggers.json`, and zero
        trial directories exist. (d) A grep check finds no option in
        `harness/run_campaign.py` that skips the check.
- [x] **Clean-tree provenance (human decision, 2026-11-07).** "Dirty" means
      `git status --porcelain --untracked-files=no` is non-empty, the same
      definition as `run.json`'s `dirty` field (AFL-008).
      - **(a) Main campaign refuses a dirty tree.** Before any main-campaign trial,
        if the tree is dirty the runner exits non-zero with a message listing the
        modified tracked files, and runs zero trials. There is no override flag
        (same reasoning as the S0 hash check). Pilots (first and confirmation) may
        run on a dirty tree; each pilot trial's `run.json` records `dirty`. Test:
        a modified tracked file makes main-campaign mode exit non-zero with no
        trial directories created; the same tree in pilot mode runs and every
        pilot `run.json` has `dirty == true`.
      - **(b) One commit per campaign.** The runner records `git rev-parse HEAD`
        at main-campaign start. Every main-campaign trial's `run.json` must have
        `commit` equal to that hash and `dirty == false`. The runner checks this
        after each trial; if any trial differs (e.g. something was committed or
        edited during an overnight run), it aborts the campaign, runs no further
        trials, and flags the offending trial(s) and both commits in the campaign
        metadata and on stderr. Test: a trial whose `run.json` has a different
        `commit` (or `dirty == true`) makes the runner exit non-zero, start no
        further trial, and name that trial.
      - **(c) Freeze enforced for targets and config, not just S0.** At
        main-campaign start, `git diff --quiet <freeze_commit> HEAD -- targets/
        experiments/configs/main.yaml` must exit 0, otherwise the runner exits
        non-zero and runs zero trials. No override. `<freeze_commit>` is the hash
        recorded at freeze time in this ticket's Log, per the AC "Pre-registered
        target retuning rule and freeze" (Freeze bullet). **Decided (human,
        2026-11-07):** the main campaign takes a required `--freeze-commit HASH`
        CLI argument, which the operator copies from the freeze Log entry.
        Rationale: a key in `main.yaml` written after the freeze would make this
        diff check fail against itself, and a git tag is mutable (`git tag -f`),
        so it is a weaker pre-registration record than a hash in the Log. Test: a
        commit after the freeze that
        changes a file under `targets/` (or `main.yaml`) makes main-campaign mode
        exit non-zero with no trial directories created; a commit that changes
        only files outside those paths proceeds.
        - **(c.i) Freeze commit resolved and checked once, up front (human
          decision, 2026-11-07).** At main-campaign start, before any trial
          runs, the runner calls the
          shared helper `resolve_freeze_commit` (AFL-008, in `src/fuzzer/cli.py`),
          which resolves the hash to 40 characters (`git rev-parse <h>^{commit}`)
          and requires `git merge-base --is-ancestor <h> HEAD`. If it raises (e.g.
          a typo, an unknown hash, or a hash from an unrelated history), the
          runner exits non-zero with the helper's message (naming the given hash
          and HEAD) and runs zero trials. No override. The runner has no freeze
          check of its own. Tests: `--freeze-commit` set to a non-existent hash,
          and to a commit not reachable from HEAD (e.g. on a side branch in a
          temporary repo), each exit non-zero with no trial directories created;
          a real ancestor proceeds; a grep check finds no `merge-base` or
          `rev-parse` call for the freeze hash in `harness/run_campaign.py`.
        - **(c.ii) Freeze commit recorded per trial, by the CLI (human decision,
          2026-11-07).** The runner uses the resolved full hash for the (c) diff
          check and passes it to every main-campaign trial's CLI invocation as
          `--freeze-commit <full hash>`; the CLI writes it to `run.json`'s
          `freeze_commit` (AFL-008). The runner never writes `run.json`; the CLI
          is its single writer. Test: invoked with an abbreviated hash, every
          trial's `run.json` has `freeze_commit` equal to the full 40-character
          hash.
      - **(d) Output cannot dirty the tree.** All campaign and pilot output is
        written under `results/`, and no file the runner or a trial writes is
        tracked by git, so the campaign cannot make its own tree dirty under the
        definition above. Which `results/` files `.gitignore` ignores is owned by
        AFL-015 (its "`results/` ignored wholesale" AC); untracked outputs never
        affect `dirty` either way. Test: after a short pilot run, `git status
        --porcelain --untracked-files=no` is empty.
- [ ] **Baseline mode (lead decision, 2026-11-15).** The runner has a baseline
      mode for the timing probe's baseline (bullet "Probe conditions: baseline
      and two official runs", *Baseline*). In it the runner runs every probe
      trial, and the crash-duration measurement, at `c` = 1, whatever
      `concurrency` `main.yaml` holds (5 from stop 2): the six counted trials,
      one per (target × schedule), one at a time (six waves of 1, no fillers),
      with the probe seeds `base_seed + 2000 + i`; and the crash-duration
      measurement with one worker, so each bug gets `R` runs. The flag is
      `--baseline`, valid only with `--kind probe` or `--crash-probe`;
      otherwise the runner refuses (exit 2). It also refuses `--k` and
      `--dmax-json` (a baseline never feeds the timeout floor), and `_dmax`
      refuses a `crash_durations.json` that carries `baseline: true`. Both
      outputs record `concurrency` 1 (the probe's `campaign.json` records it
      both top-level and in its `config` copy, so `main.yaml`'s `concurrency`
      value is not kept in a baseline's provenance) and carry `baseline: true` and the label
      "baseline: informs (d) and c, not used" (the probe in `campaign.json`
      and `probe_summary.json`; the crash-duration measurement in
      `crash_durations.json`, with `concurrency` 1 also in every CSV row).
      The baseline probe writes to `results/probe/<commit>/baseline` (or
      `results/probe/<commit>/<run-name>` with `--run-name`), the crash
      measurement to `results/probe/<commit>/baseline_crash`; `--out`
      overrides either path. The baseline probe, like every run kind other
      than the crash measurement (not only main), refuses a non-empty run
      directory, `--out` included (exit 2). Every crash measurement (`--crash-probe`, baseline or not,
      `--out` included) refuses an output directory that already holds
      `crash_durations.csv` or `crash_durations.json` (exit 2, nothing
      written); a directory holding only subdirectories or other files is
      accepted, so the official crash measurement on its default
      `results/probe/<commit>` still runs after `baseline/` and
      `baseline_crash/` exist. So the baseline never overwrites an official
      run's output, and no crash measurement overwrites another. Tests, with
      `_launch` and the executor stubbed and `main.yaml` at a `concurrency`
      above 1 (5 for (a)'s six-trial count and for (d); 3 for (a)'s
      one-at-a-time check; 4 for (b)): (a) the baseline probe launches exactly the six counted trials, one per (target ×
      schedule), never more than one at once, and no filler; (b) the baseline
      crash-duration measurement writes `concurrency` 1 in every CSV row and in
      the JSON, with `R` rows per bug; (c) both outputs carry `baseline: true`
      and the label and sit at the paths above, which no official run writes;
      (d) the same config without `--baseline` still runs at 5 (probe: two
      waves of 5; crash-duration measurement: 5 × `R` rows per bug); (e)
      `--baseline` with any other kind, with `--k` or with `--dmax-json` is
      refused, and `_dmax` refuses a baseline JSON; (f) two tests:
      `test_crash_measurement_refuses_existing_output`, where a crash
      measurement, with and without `--baseline`, whose `--out` directory
      already holds a `crash_durations.json` exits 2 and leaves that file
      untouched; and `test_baseline_then_official_crash_measurement_sequence`,
      where the baseline probe, the baseline crash measurement and then the
      official crash measurement on its default path all succeed in that
      order, and a repeat of the official crash measurement is refused
      (exit 2).
- [ ] **Abort stops running trials (lead decision, 2026-11-15).** A campaign
      abort is any of: (1) the runner's existing abort, after a trial exits
      non-zero or under AC "Clean-tree provenance" (b) (tester note T4);
      (2) the runner itself receiving SIGINT or SIGTERM; (3) a fatal runner
      error (an uncaught exception) once any trial has started. On an abort
      the runner starts no further trial, sends SIGTERM to every trial still
      running, waits at most `ABORT_GRACE_S` (10 s) in total, then sends
      SIGKILL. Each trial is launched as its own process group
      (`start_new_session`), and both signals go to the group, so they reach
      the target processes the trial runs; no process of the campaign is
      alive after the runner exits. Records in `campaign.json` (the runner
      never writes `run.json`; AC "Clean-tree provenance" (c.ii)): a trial
      stopped by the abort gets `aborted: true`; every trial that never
      started gets `{aborted: true, started: false}`, under all three
      triggers and for every run kind, probe waves never submitted included.
      Known defect, not intended behaviour (tester, 2026-11-15; fixed in
      AFL-031): under (3), a trial that was launched before the exception
      but has no record yet is also written `{aborted: true, started: false}`
      although it ran; `aborted: true` still excludes it from analysis (see
      "Known gaps"). The trial that caused an abort
      under (1) is not marked `aborted`: its record gets `error`, and the
      campaign-level `aborted` list gets `{"trial": <its directory>, "error":
      ...}`; under (2) and (3) that list gets `{"trial": null, "error": ...}`
      naming the signal or the exception. Exit status: (1) and (2) exit 1;
      under (3) the exception propagates (non-zero exit, with a traceback)
      after the trials are stopped and the records written. A stopped trial's
      partial `metrics.csv` and `crash_events.csv` are kept (AC "Partial
      streams survive an external kill") and never analysed; the mark is what
      lets AFL-012 exclude them. Tests, with the real `_launch` and
      `subprocess.Popen` stubbed to start a stub trial (a small script, not the
      fuzzer, that writes a `metrics.csv` header and one row and then sleeps;
      its SIGTERM handler writes a marker file, and one variant ignores
      SIGTERM) and `ABORT_GRACE_S` shortened in the test: for each of (1), (2)
      and (3), the stub got SIGTERM first (marker present), the
      SIGTERM-ignoring stub is killed only after the grace period, no stub
      process is alive after the runner returns, every stopped trial is
      marked `aborted: true` and every never-started trial
      `{aborted: true, started: false}`, the partial files are still on disk,
      no trial started after the abort, and the exit is 1 for (1) and (2) and
      a propagated exception for (3).
- [ ] **Smoke run kind (lead decision, 2026-11-15).** A run kind that checks
      the runner end to end before a real run. It launches one trial per
      (target × schedule), all six, at `main.yaml`'s `concurrency` (`c` = 5),
      each with `max_execs` = 200 (the CLI's `--max-execs 200`) and seed
      `base_seed + 9000 + i` (the "Seeds" table), writing to
      `results/smoke/<run-name>` (`results/smoke/smoke` without `--run-name`;
      `--out` overrides it, and the output stays excluded from analysis by
      its `excluded_from_analysis` mark).
      The kind is `smoke` (`--kind smoke`). It runs a pilot's pre-flight
      checks, the seed-set disjointness check and the cap included. It may run on uncommitted code:
      a dirty tree is recorded (`dirty` in its campaign metadata and in each
      `run.json`), not refused. The only result recorded is pass or fail: pass
      when every trial exits 0 and has a final `metrics.csv` row. The runner
      prints `smoke run: PASS` or `smoke run: FAIL`, writes `smoke_result`
      (`pass` or `fail`) and `excluded_from_analysis: true` to
      `campaign.json`, and exits 0 on pass and 1 on fail. The run is excluded
      from all analysis: nothing under `results/smoke/` is read by AFL-012 or
      AFL-014. Tests, with `subprocess.Popen` stubbed for the trial launches
      (the real `_launch` runs, so the real argv is built and `communicate`
      is called on the stub): (a) a three-target config at `concurrency: 5`
      gives six launches, one per (target × schedule), with exactly 5 live at
      once at the peak (never more), each argv with `--max-execs 200`, seed
      `base_seed + 9000 + i`, `--out` under `results/smoke/` and `--timeout` equal to the config's
      `timeout_s`; (b) on a dirty tree the run proceeds and records `dirty`
      true and `excluded_from_analysis` true; (c) all stub trials exiting 0
      with a final row print `smoke run: PASS`, record `smoke_result` `pass`
      and exit 0, and one stub trial exiting 1 prints `smoke run: FAIL`,
      records `fail` and exits 1.

## Technical notes (architect)
Harness depends on the fuzzer package, never the reverse. Keep statistics OUT of
this file (that is AFL-012); here only orchestrate + persist raw metrics.
The pilot rule is a fixed threshold on two medians, not a statistic, so it stays here.
`distinct_path_ids` has to come from the fuzzer loop's metrics (AFL-007): it keeps a
set of `path_id`s seen. Under presence-only every retained seed has a unique path, so
"distinct paths ≈ corpus size" means f(i) barely exceeds the seed's own fuzzing and
FAST cannot separate rare from frequent paths. That is what the trigger detects.
Granularity is never an arm-level knob: both arms always share it (NFR-2).

**Option, not a decision (human decision, 2026-11-13: not adopted).** If the
crash-duration measurement shows that no practical `timeout_s` satisfies
checklist item (h), one option is to run the targets with ASan `symbolize=0`
and symbolize crash reports offline. That changes how `crash_site` is computed
(ADR-0005 §3, the executor's fixed `ASAN_OPTIONS` per ADR-0002), so it would
need an ADR and a human decision before any use. It is recorded here only as an
option.

## Known gaps
- **Restart limit enforced by the operator (lead decision, 2026-11-15; tester
  note T3).** The Hang rule's *Restart from the first pilot* allows at most one
  restart for the whole project. The runner does not enforce this: it runs a
  restarted first pilot whenever asked, and writes its decision file whether
  or not the fallback already fired. The operator enforces the limit and the
  "within the allowances left" rule, from this ticket's Log.
- **`started: false` on a trial that ran (known defect; tester, 2026-11-15;
  fix in AFL-031).** When a runner exception (abort trigger (3)) is raised
  after a trial was launched but before its record was written, the exception
  handler records that trial `{aborted: true, started: false}` although it ran.
  Analysis is unaffected (aborted trials are excluded); the record is wrong.
  AFL-031 sets `started` on the record before `_launch` and adds the
  regression test.

## Test approach (tester)
Validity checklist: trial count, distinct seeds, budget honoured, reproducibility
under fixed seed. Flag any Klees anti-pattern (single-run, missing variance).
Before the freeze: confirm the freeze Log entry records a passing `pytest -m slow`
on the freeze commit itself, with at least one depth sweep per target selected.

## Re-review (reviewer, 2026-11-15)
Verdict: **APPROVE → testing.** Second review; every bounce item is fixed in the code. Two
test gaps remain (below, "Tester action"). They are not bounced because the code is correct
and the decision file stays protected even under the mutants. The tester closes them.

Gates: `ruff check .` clean; `mypy src` clean; `pytest -o addopts="" -q
tests/test_run_campaign.py -rA`: 75 passed in 6.49s. No real probe, pilot or campaign was
run. Mutants were run only in scratch copies.

Per item (file:line in harness/run_campaign.py unless noted; tests in tests/test_run_campaign.py):
- **B1 fixed.** `targets/triggers.json` has `"toy-1": "42554761"` (`b"BUGa"`) and
  `"toy-2": "21616161"` (`b"!aaa"`); the other four entries are unchanged. The `root`
  fixture copies the real file (test:81). `test_symbolizer_real_checks_every_bug`
  (test:264) derives its bug list from ground_truth.json and asserts that the pilot
  proceeds (N1). Mutant (toy entries removed): 9 tests fail, including
  `test_real_triggers_json_has_toy_entries`.
- **B2 fixed.** Tabs (:83) and duplicate keys (:92) are refused with `path:line`. nan/inf
  are refused by `_num` (:114), which names the key and the value but not the line. The AC
  asks only for the key, so this is not a blocker; the developer's Log line overstates it.
  Tests: `test_duplicate_key_refused_naming_line`, `test_tab_indentation_refused_naming_line`
  and `test_nonfinite_number_refused[...]`, all exit 2 with no results/. Each mutant is
  caught. The isfinite mutant launched unbounded trials (`seconds_per_trial: inf`); they
  were killed in scratch. Its `-inf` case is vacuous, because `<= 0` already refuses it.
- **B3 fixed.** The probe path runs through `run()` with a stubbed `_launch`:
  - `test_probe_hang_only_in_filler_violates_rule`: a hang in a filler gives exit 1,
    `hang_rule_violated` and "filler, not used";
  - `test_probe_no_hangs_exits_zero`;
  - `test_probe_summary_columns_from_known_values` and `test_probe_summary_direct`:
    exec_per_s, hang_rate, overhead and overhead per hang.

  Mutants (only counted rows checked; the `ok = False` dropped; overhead not subtracting
  `hangs × timeout_s`) are each caught by 2 tests.
- **B4 fixed.** `test_pilot_run_json_dirty_true_on_dirty_tree`: all 6 pilot run.json files
  have `dirty is True` and campaign.json has `dirty is True`. run.json is written by a stub
  that calls the real `fuzzer.cli._provenance` with cwd=root, not by the real CLI. That is
  acceptable, because run.json's writer is AFL-008's tested code. Mutant (meta dirty False)
  is caught.
- **B5 fixed in code; one test is vacuous.**
  - The decision file is refused if it exists, before any trial (:656). Test:
    `test_existing_decision_refused_never_overwritten` (both kinds; the file is
    byte-identical afterwards and nothing is launched). Caught.
  - It is written only if `ok and not missing` (:673-680). Test for the "missing" half:
    `test_pilot_trial_without_final_row_writes_no_decision`. Caught.
  - **Gap 1.** `test_aborted_pilot_writes_no_decision` passes for the wrong reason: its
    failing stub writes no metrics.csv, so `missing` is non-empty. Mutant
    `if ok and not missing` → `if not missing` survives the whole suite. It is reachable
    when the abort comes from a trial that already wrote its final row (for example the
    last trial).
  - **Gap 2.** `final_row`'s half-written-row handling (:370-373) has no test; mutant
    survives. Under that mutant a half row raises (traceback, no decision written), so no
    wrong decision can result.
- **B6 fixed.** :582-585 resolves the config path and refuses anything but
  `root/experiments/configs/main.yaml` for `--kind main`. Tests:
  `test_main_refuses_other_config` (exit 2, "main.yaml", no results/) and
  `test_pilot_accepts_other_config`. Caught.
- **N2 fixed.** :616-618 refuses commit `unknown` (`test_crash_probe_refuses_unknown_commit`);
  `dirty` is recorded in crash_durations.json (:542; `test_crash_probe_outputs` asserts
  `dirty is True`; mutant caught). The unknown-commit mutant was not run: it would run a
  real crash probe. Reasoned instead: without the guard, run() proceeds, so the test's
  `== 2` fails.
- **N4 fixed.** :257-260 (`test_target_path_must_match_launch_path`). Mutant not run, since
  it would launch real pilot trials. Reasoned instead: without the guard, the pilot
  returns 0 and the test's `== 2` fails.
- **N5 fixed.** :587-589 (`test_main_refuses_fewer_than_ten_trials`, exit 2, "got 9").
  Caught.
- **N6 fixed.** `_dmax` (:568-575): a missing file, bad JSON, a missing key or a
  non-number gives a refusal and no traceback (`test_dmax_json_bad_file_clear_refusal`, 4
  cases). Mutant caught 4/4.
- **N7 fixed.** :414-415 (`test_launch_pythonpath_has_no_empty_entry[-SRC]`). Caught.
- **Nothing weakened.** Diffed against the pre-fix test file reconstructed from the fix
  session:
  - The `trials_per_config` default changing 2 → 10 affects no assertion; every
    count-sensitive test sets its own value or uses PILOT_TRIALS.
  - `planned` writing metrics.csv is needed so stubbed pilots complete; no assertion was
    dropped.
  - `test_real_main_full_freeze_hash_and_clean` went from 1 trial to 10, and asserts all 10
    plus seeds 7..16. That is stronger.
  - The crash-probe tests now run in git and assert the commit path and `dirty`.
  - The concurrency test now stubs `_launch` rather than `execute`.
  - The `_launch` NFR-2 arguments are unchanged apart from PYTHONPATH. mutator.py and
    schedule.py have no diff.

Tester action (condition of the testing gate): add these two tests. Both pass on the
current code and kill the two surviving mutants; verified in scratch.
1. Pilot with concurrency 1. Every stubbed trial writes a final row; the 6th trial
   returns exit 1. Assert exit 1, 6 launches, and no `results/pilot/granularity_decision.json`.
2. `final_row` on metrics.csv with a full row followed by `10.5,12` returns None.

Crash-probe exemption from B6/N5 (opinion, not blocking):
- It is right. The freeze diff check and the ≥10-trial rule are about the main campaign.
  The crash probe runs no trials.
- The baseline crash measurement needs `c = 1` while main.yaml carries the campaign `c`.
  A separate config, or the exemption, is needed for that.
- Suggestion: `crash_durations.json` should record the config path and its sha256, plus
  the `timeout_s` used for the floor. A measurement taken on a non-main config would then
  be visible in the record itself, not only in shell history.

New non-blocking notes:
- R1. The decision path is `run_dir.parent`, so `--out` lets a second first pilot write
  its decision file in another directory. The once-only rule is enforced only for the
  default layout. Consider refusing `--out` for FIRST_PILOTS, or always writing the
  decision to `root/results/pilot/`.
- R2. The B2 isfinite mutant showed that a trial with an infinite budget runs unbounded.
  That supports N3 (subprocess timeout, with the lead).

## Test (tester, 2026-11-15)
Verdict: **PASS for every code-checkable AC.** The ticket stays in `tickets/testing/`. The
run-time ACs below stay open until the real runs; whether and when those run is the user's
decision. This ticket bounced once in review (2026-11-15) and was approved on re-review.

No real probe, pilot, main campaign or crash probe was run, and no `fuzzer.cli` trial was
started outside pytest's existing tests. Every mutant ran in a scratch copy, under a 120 s
process-group timeout. In that copy a conftest guard replaced `_launch` with a stub, so no
real launch was possible. `pgrep -fl 'fuzzer[.]cli'` was empty after every run.

**Gates (repo, unmodified tree):**
- `.venv/bin/ruff check .`: All checks passed!
- `.venv/bin/mypy src`: Success: no issues found in 8 source files
- `.venv/bin/pytest -o addopts="" -q tests/test_run_campaign.py tests/test_cli.py
  tests/test_fuzzer.py -rA`: 142 passed in 77.72s. This includes 77 in
  test_run_campaign.py. The real-binary tests passed: `test_symbolizer_real_checks_every_bug`,
  `test_real_pilot_records_everything`, `test_real_main_full_freeze_hash_and_clean` and
  `test_streams_survive_sigkill`, along with `test_fuzzer.py::test_replay_same_seed_identical_different_seed_differs`.

**Re-review condition (B5).** Both tests exist and pass:
`test_aborted_pilot_with_all_final_rows_writes_no_decision` and
`test_final_row_half_written_last_row_is_none`. Mutant `if ok and not missing` →
`if not missing` is caught by the first test only. Mutant replacing the
`except (ValueError, TypeError)` half-row guard is caught by the second test only. Condition met.

**Per-AC status** (met = verified at code level with tests; open = needs real run, user decision):

| AC | Status |
|---|---|
| Reads main.yaml | met (`test_real_main_yaml_parses`; checkbox still unticked) |
| ≥10 trials, `base_seed + i`, cap 1000 | met |
| Seed sets disjoint at campaign start | met |
| Honours `seconds_per_trial`, per-trial metrics | met in code (`--seconds` passed, metrics/crash_events from AFL-007); open: 600 s budget honoured in a real run |
| Commit + exact command (NFR-1) | met (campaign.json `commit`, `command`; run.json `commit`, `argv`) |
| Exec-index replay | met in code (AFL-007 replay test passes; seed and argv recorded); open: replay of an actual campaign trial |
| `distinct_path_ids`, `corpus_size` | met (AFL-007 `METRICS_COLUMNS`) |
| Partial streams survive SIGKILL | met |
| Pilot + granularity fallback | met in code (rule, once-only file, B5); open: the first pilot itself, decision recorded in ADR-0001 |
| Retuning rule and freeze | runner parts met (seed table, freeze diff); open: pilots, retune evaluation, freeze hash, depth sweeps and clean rebuilds on the freeze commit, timing probe |
| Pre-freeze checklist (a)–(k) | open, all items (runner support for probe layout, probe_summary, crash probe and `--k` floor is met in code) |
| Timeout and concurrency from config | met (main.yaml values are placeholders, with the lead) |
| Campaign machine recorded | met |
| ≥3 targets | met |
| Initial corpus = S0 | met |
| Pre-flight S0 integrity | met |
| Pre-flight symbolizer | met in code (tests (a)–(d) pass, (a) on real binaries; checkbox still unticked); open: its pass at the start of each real run |
| Clean-tree provenance (a)–(d) | met |

**Seed sets computed from the code** (real main.yaml, `base_seed` 1000, 10 trials):
- Ranges: main 1000..1009; first pilot 2000..2002; probe 3000 (c ≤ 3, three targets) or
  3000..3001 (fillers); confirmation pilot 4000..4002; restarted first pilot 5000..5002;
  restarted confirmation pilot 6000..6002.
- Checked for 3 and 2 targets at c = 1, 3, 5, 10. The six sets were pairwise disjoint in
  every case, and every planned trial's seed was in its run kind's recorded set.
- Within each target, the arms share seeds.
- 999 trials with `base_seed` 0 is disjoint (main 0..998). 1000 trials is refused by the cap.

**Case table:**
- Three targets: c = 5 gives 5 + 5 with 4 fillers; c = 3 gives 3 + 3 with no fillers.
- Two targets:
  - c = 5 gives one wave of 4 counted trials plus 1 filler.
  - c = 3 gives a wave of 3, then 1 counted trial plus 2 fillers.
  - Pilot 12 trials, main 40.
- Fillers continue the round-robin with i = 1, 2, …; arms alternate.
- All match the pre-registered tables. m = 4 is AFL-012's rule and is not runner code.

**Mutation (31 mutants, scratch):** 30 caught, 1 survived. The survivor is benign: the
`sysctl` non-zero-exit refusal, which test (e) does not isolate because its exit-1 case has
empty output. A direct check of the unmutated code (exit 1 with output `8`) refuses as
required.
- The scratch-only checks were for:
  - NFR-2 argv identity across arms;
  - `--timeout` equal to the config value in every run kind;
  - at most `concurrency` trials at once;
  - the probe wave barrier;
  - the symbolizer getting the config `timeout_s`;
  - the confirmation pilot writing no decision;
  - an empty or whitespace `--allow-fewer-targets` reason;
  - concurrency equal to the core count proceeding.
- These mutants were killed only by scratch-only checks (not added to the repo):
  - `--timeout` dropped;
  - `--seeds` differing by arm;
  - the symbolizer at 1.0;
  - the confirmation pilot writing a decision;
  - no wave barrier;
  - the empty-reason guard removed.
- In the repo suite only the real-trial test `test_real_pilot_records_everything` pins
  `--timeout` and the seed corpus.

**Non-blocking notes** (for the developer, as a follow-up ticket if wanted):
- T1. Port the scratch checks above into `tests/test_run_campaign.py` as stubbed tests, so
  that NFR-2, `--timeout`, the wave barrier and the symbolizer timeout are pinned without real
  trials.
- T2. Make test (e)'s exit-status case return digits with exit 1, so the exit check is
  isolated.
- T3. The runner writes the restarted first pilot's decision file whether or not the
  fallback already fired; "within the allowances left" is enforced by the operator, not the
  runner.
- T4. On an abort, sibling trials already running are not killed and run their full budget.
  This is consistent with "no further trial", and relates to N3.

Already with the lead and not judged here: N3, P2, P3, the main.yaml placeholders, PyYAML
versus the hand parser, baseline detection, the crash-probe overwrite, R1 and the crash-probe
exemption from B6/N5.

## Log
- 2026-11-__ — created (req-engineer)
- 2026-11-07 — added distinct_path_ids metric and pre-registered pilot fallback
  (presence-only → hit-count buckets) per human decision; see ADR-0001 (architect)
- 2026-11-07 — note (human decision, via AFL-003): time-to-first-crash counts only
  executions with `outcome == "crash"`, never hangs (`outcome == "hang"`). Also: the
  fork-server decision is made here with real AFL-003 throughput numbers. Build one
  (new ticket, both arms) only if the measured execs/s make the campaign infeasible in
  the time available (architect)
- 2026-11-07 — added ≥3-targets AC (PRD §8 line 103): refuse by default, recorded
  override per PRD §11. Added AFL-016 (third target) to depends_on (req-engineer)
- 2026-11-07 — per human decisions: depends_on += AFL-009, AFL-010 (all three
  experiment targets must exist with their ≥2 planted bugs). Added a pilot
  cross-reference to AFL-016's retuning/freeze rule (req-engineer)
- 2026-11-07 — per human decisions: this ticket now holds the canonical
  "Pre-registered target retuning rule and freeze" AC. It covers every deep bug
  (toy-1, tlv-2, mfp-1). Both pilot rules are evaluated once, on the first pilot.
  One confirmation pilot follows, and it never re-triggers either rule. The freeze
  hash is logged here and in each target ticket. The AFL-016 rule AC is now a
  pointer here (req-engineer)
- 2026-11-07 — added three-way-disjoint seed clause to the retuning rule (human decision) (req-engineer)
- 2026-11-07 — per human decision: added "Initial corpus = S0" AC
  (`targets/seeds/<target>/`, only S0, both arms, recorded in metadata). The
  pre-registered block is unchanged (req-engineer)
- 2026-11-07 — added S0 integrity pre-flight AC (human decision) (req-engineer)
- 2026-11-07 — batch grooming: reproducibility AC reworded to exec-index replay (AFL-007 / ADR-0005); AFL-019's ACs folded into the S0 pre-flight AC block (zero-length S0 rejected, test, mutator.py unchanged, reachability comment) (human decision) (req-engineer)
- 2026-11-07 — review fix: added "Clean-tree provenance" AC: (a) main campaign aborts on a dirty tree (tracked changes only), no override, pilots may run dirty and record it; (b) one commit per campaign, every main trial's run.json has the start commit and dirty == false, else abort and flag; (c) `git diff --quiet <freeze_commit> HEAD -- targets/ experiments/configs/main.yaml` must pass, no override, freeze_commit = hash logged at freeze time; (d) output under results/, nothing written is tracked; .gitignore covers results/ only for *.json/*.png/*.csv (human decision) (req-engineer)
- 2026-11-07 — review fix: freeze hash supplied via required `--freeze-commit HASH` (copied from the freeze Log entry; not main.yaml, which would fail its own diff check; not a tag, which is mutable); added (c.i) `git merge-base --is-ancestor` check aborting loudly and (c.ii) full 40-char `freeze_commit` in every trial's run.json, each with a test (human decision) (req-engineer)
- 2026-11-07 — review fix: (c.i) now calls AFL-008's shared `resolve_freeze_commit` helper once at campaign start, before any trial (no runner-side freeze check, grep test); (c.ii) runner passes the resolved hash to each trial's CLI via `--freeze-commit`, CLI stays run.json's single writer; (d) stale `.gitignore` fact removed, points to AFL-015 (human decision) (req-engineer)
- 2026-11-12 — added pre-freeze checklist item to the freeze AC: `pytest -m slow` (the S0 depth sweeps, excluded from the default run) passes on the frozen tree, one sweep per target, recorded in the freeze Log entry (human decision) (req-engineer)
- 2026-11-12 — added pre-run checklist item to the freeze AC: `make -C targets clean all` exits 0 before the first pilot, the confirmation pilot (if any) and the main campaign, and before the depth sweeps on the candidate freeze commit, recorded in each run's Log entry. Reason: the AFL-009 reviewer found stale binaries, since `targets/bin/*` do not depend on the Makefile and a flag change is not rebuilt (human decision) (req-engineer)
- 2026-11-12 — added pre-freeze timing-probe item to the freeze AC: after M1 and before the freeze, exec/s per target with nothing else running and toy_parser's hang rate (any nonzero rate means machine load affects timeouts and is a reason to raise `--timeout` before the freeze, since timeouts are the disclosed replay exception); both numbers recorded in the freeze Log entry (human decision) (req-engineer)
- 2026-11-12 — added to the S0 pre-flight block: each target's seeds dir must hold exactly {S0} among non-hidden files (AFL-007's seed-file function), else abort before any trial, no override; `.DS_Store` ignored, stray `S1` aborts, both tested. "Initial corpus = S0" now records hashes of seed files only, not every file (human decision, 2026-11-12) (req-engineer)
- 2026-11-12 — added AC "Pre-freeze checklist", directly after the freeze AC, whose text is unchanged: (a) AFL-015/018/027/028 in `tickets/done/`, (b) `pytest -m slow` on every target against the frozen S0s, (c) timing probe run and PRD §8 (vii) states measured exec/s, (d) user's parallel-trials vs fork-server decision, (e) clean tree and everything pushed; each item ticked in this Log with date and evidence before the freeze commit. The timing-probe amendment (hang count and rate per target; AFL-028 drain cost as hang count and total hang `exec_time`, expected 0 on toy_parser) sits in that AC as "Timing-probe additions", because the probe item lives inside the freeze AC, which is not edited. The human chose a freeze checklist over adding AFL-015, AFL-018, AFL-027 and AFL-028 to `depends_on`, because only the freeze event depends on them and the implementation of this ticket is not blocked (human decision, 2026-11-12) (req-engineer)
- 2026-11-12 — "Timing-probe additions" rewritten: the hang-time source is
  AFL-007's new `metrics.csv` column `hang_time_s` (human decision, 2026-11-12;
  architect confirmed). Beyond what the freeze AC's item "Pre-freeze check: timing
  probe" measures (exec/s, toy_parser's hang rate, not restated), the probe reports
  per experiment target the final `hangs`, the final `hang_time_s` and the hang
  overhead `hang_time_s − hangs × timeout_s` (and per hang when `hangs > 0`);
  expected for toy_parser 0, 0.0 and 0.0. The "architect specifies the source
  later" sentence is removed. The freeze AC and checklist item (c) are unchanged
  (architect)
- 2026-11-12 — AC "Pre-freeze checklist": added item (f), a clean rebuild
  (`make -C targets clean all`) on the commit being frozen, before (b) and before
  the timing probe in (c); and item (g), a `toy-1` calibration prediction written
  in this Log before any pilot trial. The freeze AC and items (a)–(e) are
  unchanged (human decision, 2026-11-12) (req-engineer)
- 2026-11-12 — **Calibration prediction for `toy-1`, recorded before any pilot
  trial (checklist item (g); human decision, 2026-11-12)** (req-engineer).
  - *Status.* This is a qualitative calibration expectation, not a hypothesis
    test. It is not part of H1 or of the primary family (AFL-012), and no
    statistic is computed on it. The report compares the pilot's `toy-1` find
    rate in each arm with it. It does not change the retuning rule: that rule's
    triggers are evaluated on the first pilot exactly as written.
  - *Prediction.* In the pilot, `toy-1` is found in some trials but not in all,
    in each arm (UNIFORM and FAST). That is a discriminating find rate, neither
    0 % nor 100 %.
  - *Measured inputs.* Per-mutant step odds measured by the AFL-009 reviewer
    with the real `mutate()`, 200,000 mutants each (AFL-009 Log, re-review
    2026-11-12): `aaaa` → `B*` 2.6e-3, `Baaa` → `BU*` 3.1e-4, `BUaa` → `BUG*`
    1.4e-4, and `aaaa` → `BUG*` directly 0. Budget: about 9,000 executions per
    trial (AFL-007 measured about 15 exec/s; 15 × 600 s). The timing probe in
    (c) will refine this. The energy is spread across several corpus seeds, so
    the staircase seed of the current step gets only part of the budget.
  - *Arithmetic.* Assume each mutant of a staircase seed reaches the next step
    independently with the measured odds p, so the number of mutants a step
    needs has mean 1/p. If every execution went to the current staircase seed,
    the expected total would be 1/2.6e-3 + 1/3.1e-4 + 1/1.4e-4 ≈ 385 + 3,226 +
    7,143 ≈ 10,750 mutants. That is more than the 9,000-execution budget, and
    the staircase seeds get less than all of it, so a find in every trial is
    not expected. The waiting times vary widely (for a geometric count the
    standard deviation is close to the mean), so some trials finish the
    staircase well under its mean, and a find in some trials is possible. The
    arithmetic supports "not in every trial" more firmly than "in at least one
    trial": how small the staircase seeds' share of the budget is decides how
    often a trial finishes in time.
  - *No numeric interval.* The share of the budget each staircase seed gets is
    not known before the pilot, and it differs between arms (UNIFORM gives 256
    per selection; FAST's energy depends on s(i) and f(i)). The measured odds
    therefore do not fix a per-trial find probability, and none is stated.
  - *Small pilot.* With 3 pilot trials per arm, an arm with 0 or 3 finds can
    occur even when the true rate is in between. Such a result is reported as a
    miss of this prediction, not explained away.
- 2026-11-12 — metrics AC: `distinct_path_ids` is counted over clean and crash
  executions, never hangs (was "over all execs"), matching AFL-007's loop and
  ADR-0005 §5 (AFL-007 reviewer note (f)). The phrase did not occur in the pilot
  trigger, the retuning rule or the freeze block, which are unchanged (human
  decision, 2026-11-12) (req-engineer)
- 2026-11-12 — added AC "Pre-flight symbolizer check": at the start of every
  campaign (pilots and main), toy-2's trigger `b"!aaa"` is run through the
  executor against `targets/bin/toy_parser` and `crash_site()` must return
  toy-2's `function` from `ground_truth.json` (`"scan"`), else abort with zero
  trials and a symbolizer error; no override flag. Resolves ADR-0005's open
  question "Symbolizer check" (one trigger, toy-2 only). Checklist item (b) is
  unchanged; the new AC states it is not a substitute (human decision,
  2026-11-12) (req-engineer)
- 2026-11-12 — AC "Pre-flight symbolizer check" revised (human decision,
  2026-11-12: supersedes toy-2-only). The Scope line "One trigger, toy-2 only
  (human decision; ADR-0005's recommendation of one trigger per planted bug was
  not adopted)" is replaced: ADR-0005's "Symbolizer check" recommendation is
  adopted, one known trigger per planted bug in `ground_truth.json` for every
  campaign target, each `crash_site()` must equal the bug's `function`, any
  failure aborts with zero trials. Triggers live in `targets/triggers.json`
  (bug id → hex; no field in `ground_truth.json`; toy-1 `b"BUGa"`, toy-2
  `b"!aaa"`); a bug with no entry aborts. "What it does", "Pass condition",
  "Otherwise abort" and "Tests" reworded to match; "Missing trigger aborts" and
  "Trigger table" added; "No override" unchanged except "binary" → "binaries".
  AFL-010 and AFL-016 each gained an AC for their entries (req-engineer)
- 2026-11-13 — slow crashes lost as hangs: under CPU load ASan crash reporting
  (mostly symbolization) ran past the 1 s timeout, and the executor ranks hang
  above crash (`test_asan_crash_despite_parent_env` failed 129/600 under 20
  `yes` processes; `test_toy1_deep`, `test_toy2_shallow`, `test_fixture_not_stale`
  also failed). Added to "Pre-freeze checklist": item (h), `timeout_s ≥ k ×
  D_max` with `k` chosen before any pilot from the measured crash durations
  (fields to fill in, no value set); item (i), concurrency ≤ `sysctl -n
  hw.physicalcpu`; bullet "Crash-duration measurement" (`--crash-probe`: every
  planted bug's trigger at the planned concurrency, alone on the machine, on
  committed code after `make -C targets clean all`, before the first pilot and
  on the candidate freeze commit, recorded in
  `results/probe/<commit>/crash_durations.{csv,json}` and the Log). New AC
  "Campaign timeout and concurrency from the config" (required `timeout_s` and
  `concurrency` in main.yaml, passed as `--timeout` to every trial and used by
  the symbolizer pre-flight, cap enforced, no override). New AC "Partial streams
  survive an external kill" (line-buffered metrics.csv and crash_events.csv,
  flushed at run end; changes `src/fuzzer/fuzzer.py`, AFL-007 being closed;
  SIGKILL test). Technical note: ASan `symbolize=0` with offline symbolization
  recorded as an option only, not adopted. Reconciled, not duplicated: the
  freeze AC's item "Pre-freeze check: timing probe" is unchanged; (h) states its
  "`--timeout` value frozen" is the same number as `timeout_s`, and its
  nonzero-hang-rate reason to raise `--timeout` still applies above the floor.
  Item (c) is unchanged and now also covers the new measurement (it sits under
  "with the additions below"). The "Pre-flight symbolizer check" text is
  unchanged; the new config AC fixes its timeout. `module` += main.yaml and
  fuzzer.py. PRD §8's "Timing-dependent hangs" entry needs a matching update,
  proposed to the human, not made (human decision, 2026-11-13) (req-engineer)
- 2026-11-13 — human decisions on the 2026-11-13 additions (human decision,
  2026-11-13) (req-engineer):
  (1) item (h): interpretation confirmed, the measurement runs twice (before
  the first pilot, which fixes `k`, and on the candidate freeze commit); a
  violation on the second run raises `timeout_s` with `k` unchanged, and a
  lower pilot timeout is recorded. New bullet "Two probe runs; conservative
  value": the timing probe runs at both points, both runs' values are recorded,
  and on substantial disagreement the lower exec/s and the longer crash
  duration are used. For crash duration (h)'s every-run floor already makes the
  larger `D_max` govern, so no threshold is needed; for exec/s a definition of
  "substantially" is PROPOSED, awaiting human confirmation (any difference, or
  lower < 90 % of higher), and item (c) is not ticked until it is confirmed.
  (2) item (i) and AC "Campaign timeout and concurrency from the config":
  interpretation confirmed, `concurrency` is a required key and the
  `hw.physicalcpu` cap is a refusal at campaign start with no override flag
  (no option, environment variable or config key); test (d), a grep check for
  a bypass, added.
  (3) "Crash-duration measurement": interface confirmed as written.
  (4) PRD §8 "Timing-dependent hangs" is not edited now: new checklist item
  (j) rewrites it from the template held in (j), with the measured `k`,
  `D_max`, `timeout_s` and `c`, after the freeze-commit probe run, and the
  human reads it as pre-registration text before the freeze commit.
  `docs/PRD.md` unchanged.
  (5) item (h) notes that ADR-0005 §4 references this rule; the note itself is
  approved and is written by the architect. `docs/adr/` unchanged.
- 2026-11-13 — reproducibility AC: `metrics.csv`'s `hang_time_s` named next to
  `elapsed_s` as a wall-clock field excluded from replay. This aligns the AC
  with ADR-0005 §3; no new decision (architect note) (req-engineer)
- 2026-11-13 — bullet "Two probe runs; conservative value" amended: the whole
  timing probe runs twice; the conservative value is always used per target
  (lower exec/s, larger `D_max`, which sets `timeout_s` via `k`, higher hang
  rate), which resolves the exec/s "substantially" proposal; the freeze Log
  entry tables both runs per target and metric; a divergence check
  (`|a − b| / max(a, b) > 0.20` on any of these) stops the probe values from
  being used until the cause is investigated and the human decides. The
  hang-rate floor (skip the relative check when `max(a, b) < 0.001`) is OPEN,
  proposed, human to confirm, and item (c) is not ticked until it is (human
  decision, 2026-11-13) (req-engineer)
- 2026-11-13 — hang-rate floor replaced by an absolute rule: any hang in either probe run on any target stops the freeze until the cause is found and the human decides; the 20% rule now covers exec/s and D_max only (human decision, 2026-11-13) (req-engineer)
- 2026-11-13 — item (j) template widened to every target and both runs; PRD §8 threats line widened to match (human decision, 2026-11-13) (req-engineer) ; freeze AC Log-record sentence widened to match
- 2026-11-13 — item (j) hang blanks labelled per target and per run (toy_parser, tlv_parser, mini_format; run 1 / run 2) (human decision, 2026-11-13) (req-engineer)
- 2026-11-13 — probe conditions: new bullet "Probe conditions: baseline and two official runs". A concurrency-1 baseline (the six trials one at a time and the crash-duration measurement at `c` = 1, committed code, clean rebuild, nothing else running) runs before the first official run, is labelled "baseline: informs (d) and c, not used", informs (d) and `c`, and is outside the divergence check and the hang rule. The two official runs (before the first pilot and on the candidate freeze commit) each launch one trial per (target × schedule), six in all, `c` at a time with the arms interleaved, plus the crash-duration measurement at `c`; exec/s and hangs recorded per (target, schedule); the conservative value per target is the lower exec/s and higher hang count over both schedules and both official runs, the larger `D_max` still governs (h). Order fixed: baseline, then (d) and `c`, then the first official run (fixes `k`), then the first pilot. PRD §8 (vii), (d)'s decision record and (j) use official values only. Amended in place: the freeze AC's timing-probe item (pointer to the new bullet; Log-record sentence now per (target, schedule) in both official runs), (d) evidence, (h) `k` from the first official run, (i) `c` from the baseline and used by both official runs, "Timing-probe additions" per (target, schedule), "Two probe runs" table, conservative value and "used", divergence check, hang rule and tester *Check* (human decision, 2026-11-13) (req-engineer)
- 2026-11-13 — concurrency cap, macOS only: the campaign machine is this Mac (macOS, Homebrew LLVM), its physical core count from `sysctl -n hw.physicalcpu` (item (i)); new AC "Campaign machine recorded" (model, macOS version, clang version, `hw.physicalcpu` in the campaign metadata, with a stubbed-command test); item (i) and the config AC refuse to start, with no trial directories, when `sysctl` fails or is not found, prints nothing, or prints something that is not a positive integer, never skipping the cap, with test (e) stubbing each case; PRD §8 threats gained an entry recording the departure from NFR-4 (human decision, 2026-11-13) (req-engineer)
- 2026-11-13 — consistency: stale 'unchanged' statements, toy_parser-only expected values, the (j) blank definition (higher of the two schedules) and the baseline's crash-duration run made consistent with the 2026-11-13 decisions (req-engineer)
- 2026-11-13 — three probe decisions (human decision, 2026-11-13) (req-engineer). D1, reaching `c` when `c` > 6: each official run launches r = ⌈c/6⌉ trials per (target × schedule), 6r in all, `c` at a time with the arms interleaved, replica 1 of every (target, schedule) in the first wave; conservative values come only from full-wave trials, partial-final-wave trials are recorded as "not at full load, not used"; worked example `c` = 10; freeze Log table gains replica, seed, wave and used columns; OPEN: `c` = 4 or 5 leaves a partial final wave. D2, probe trial length and seeds: every probe trial runs `seconds_per_trial`; seeds `base_seed + 2000 + i`, added to the freeze AC's pairwise-disjoint "Seeds" rule; baseline r = 1 (six sequential trials); crash-duration measurement uses no RNG; OPEN: whether the baseline and official runs share probe seeds. D3, (d) and `c` re-decided at most once: decided from the baseline, the record states its rule, the first official run is checked against that rule, at most one revision before the first pilot, a changed `c` repeats the first official run and `k` comes from the repeat; replaces the earlier reconciliation in (d); OPEN: a change to (d) without a change to `c`. `docs/PRD.md` unchanged: the pairwise-disjoint seed rule is not in it
- 2026-11-13 — seven probe and seed decisions E1–E7 (human decision, 2026-11-13) (req-engineer). E1, waves and fillers, replacing D1 (the ⌈c/6⌉-replica rule, the partial-wave "not at full load, not used" rule, the replica column and the `c` = 4/5 OPEN are gone): every probe run is full waves of exactly `c` trials, six counted trials (one per (target × schedule)) plus fillers that complete the last wave; fillers are real trials of the campaign targets in the same round-robin order, recorded as "filler, not used", excluded from every exec/s and `D_max` value, covered by the hang rule; case table for `c` = 1, 4, 5, 6, 10; divergence check unchanged (one counted value per (target, schedule) per run); conservative value, "higher hang count" sub-bullet and tester *Check* say "counted trials only; filler rows never supply a used value"; Log table rows per probe trial with seed, wave and "counted"/"filler, not used"; launch mechanism left to the architect. E2, probe seeds: the same seeds in the baseline, the first official run (and any repeat) and the second official run; counted trial `i = i₀` (the main campaign's first index), fillers continue `i` within their (target, schedule) in round-robin order; the seed-sharing OPEN is gone. E3, any revision of (d) or `c` (at most once, before the first pilot) repeats the first official run and `k` comes from the repeat; a fork server is its own ticket, run 1 repeated after it lands; the (d)-without-`c` OPEN is gone; (d), (h) and the *Order* note updated. E4, confirmation pilot seeds `base_seed + 3000 + i`; all four ranges in one table in the "Seeds" bullet. E5, every run kind has fewer than 1000 trials per (target, schedule); the runner refuses a config at or above the cap. E6, new AC "Seed sets disjoint, checked at campaign start" with a refusal test. E7, hang rule covers every probe trial, counted or filler, baseline included (replaces "the baseline is outside this rule"; *Baseline* bullet and "Which runs count" updated); (j) definition says counted trials; PRD §8 monitor sentence and ADR-0005 §4 Monitoring paragraph and cross-reference widened to match. Earlier Log lines kept as history; where they mention replicas, `r`, partial waves or the OPEN notes, this line supersedes them
- 2026-11-13 — three follow-ups F1–F3 (human decision, 2026-11-13) (req-engineer). F1, Hang rule gains *What is rerun*: after a `--timeout` raise only the two official runs are rerun by default; (a) a baseline hang also reruns the baseline; (b) a fixed target bug reruns the depth sweeps (freeze AC "Pre-freeze check: depth sweeps on the frozen S0", checklist (b)), the baseline and both official runs, with any resulting change to (d) or `c` under item (d)'s at-most-one-revision-before-the-first-pilot rule; OPEN: (b) arising after the first pilot (a hang in the second official run) is outside that bound. F2, "Two probe runs" freeze Log table now one row per probe trial, fillers included, with run, target, schedule, seed, wave and "counted"/"filler, not used" columns; the trailing note trimmed to the no-replica-column pointer. F3, ADR-0005 §4 Monitoring: "nothing else running on the machine besides the probe's own trials"
- 2026-11-14 — G1–G2 (human decision, 2026-11-14) (req-engineer). G1, the OPEN on exception (b) after the first pilot is replaced by the Hang rule sub-bullet *Restart from the first pilot*: a target bug fixed after the first pilot has started restarts the pre-freeze sequence once, from the first pilot; trigger is a committed, logged reproducer that hangs at `c` = 1 with a generous timeout; minimal fix, target ticket ACs and depth sweeps still pass, fix logged in the target ticket; at most one restart per project; fresh seeds `base_seed + 4000 + i` (restarted first pilot) and `base_seed + 5000 + i` (restarted confirmation pilot), added to the "Seeds" table and rule, the cap's run kinds and the AC "Seed sets disjoint, checked at campaign start"; allowances already used stay used (retunes, granularity fallback, the one (d)/`c` revision; `k` unchanged), triggers evaluated only within what is left; original pilot data kept, labelled "superseded by restart", reported; no time to restart means excluding the target via `--allow-fewer-targets "<reason>"` (AC "≥3 targets (PRD §8)"), the primary family losing its two members per AFL-012. Made consistent: retuning rule "When evaluated" and "Limit", granularity fallback decision rule, item (d)'s revision bound and the *Order* note. G2, "Investigate" now points at *What is rerun* instead of "run the whole probe again (both runs)"
- 2026-11-14 — H1–H4 (human decision, 2026-11-14) (req-engineer). H1, restart order confirmed and stated in full (fix → depth sweeps for the fixed target → baseline → first official run → restarted first pilot → any retune and restarted confirmation pilot → depth sweeps and second official run on the candidate freeze commit); "Minimal fix" requires the fixed target's depth sweeps to pass straight after the fix. H2, `k` unchanged after a restart confirmed (a margin, not a duration; a slower fixed binary raises `timeout_s`, not `k`); new item (h) bullet: superseded official runs (under (d) or by a restart) still count towards the `D_max` floor, the baseline still outside it; item (d)'s "superseded: ran at c = ____, not used" clarified to mean not used for exec/s, hangs and `k`, not for the floor. H3, a restarted confirmation pilot runs only after a retune or granularity change on the restarted first pilot; the fix itself needs none (confirmed). H4, superseded pilot data kept under `results/`, location the architect's choice
- 2026-11-14 — I1–I3 (human decision, 2026-11-14) (req-engineer). I1, baseline `D_max` outside the floor confirmed in item (h)'s "Superseded runs count towards the floor" bullet (the floor protects against crashes lost as hangs under campaign load; the baseline measures at `c` = 1 on an otherwise idle machine); the "Probe conditions" `c` = 1 sentence now says the official runs still happen as separate runs and only they count towards the floor and supply used values. I2, "Two probe runs; conservative value" crash-duration sub-bullet points at item (h)'s superseded-runs bullet. I3, item (h) evidence template gains "superseded run `D_max` = ____ s (bug ____, commit ____; ____ if none)"
- 2026-11-14 — "Pre-freeze checklist" item (a): AFL-030 added (option A chosen; its implementation lands before the freeze); evidence now lists all five ticket files (human decision, 2026-11-14) (req-engineer)
- 2026-11-14 — three lead decisions (lead decision, 2026-11-14) (req-engineer). (1) Item (d) gains its stated rule: parallel trials, no fork server, `c` = 5; the one permitted revision is to `c` = 3 if the first official run's per-trial exec/s falls below 80 % of the baseline's, otherwise `c` stays 5; comparison per target, the first official run's conservative per-target exec/s against the baseline's for the same target, revise if any campaign target is below 80 % (interpretation, pending lead confirmation); item (i), the *Order* note and the waves table (`c` = 3 row) made consistent; the existing machinery (decided from the baseline, at most one revision before the first pilot, the repeat at the new `c` fixes `k`, the superseded run's `D_max` still counts towards the floor) unchanged. (2) AC "≥3 targets (PRD §8)" gains the AFL-016 cutoff: not in `tickets/done/` by the end of 2026-11-16 means the campaign runs without it under `--allow-fewer-targets "<reason>"` and the report discloses the exclusion; `depends_on` left as is, reconciled in that AC. (3) New checklist item (k): every planted bug of every campaign target is ASan-reported with a stack at a target function, is not an integer divide by zero, and the source passes AFL-030's static source check (list kept in AFL-030 only); PRD §8 threats gained a matching line after the platform line
- 2026-11-15 — lead decisions (lead decision, 2026-11-14) (req-engineer): (a) 80% comparison confirmed, c = 3 kept if also below 80%, disclosure sentence in PRD §8; (b) AFL-016 cutoff is an event: in done and committed before the baseline starts (scheduled 2026-11-16 12:00 ET), else two targets with --allow-fewer-targets, no later addition; (c) two-target probe case added.
- 2026-11-15 — lead decisions (lead decision, 2026-11-15) (req-engineer): (1) AFL-016 cutoff redefined as readiness, not the commit: AFL-016 in `tickets/done/`, closed by the crew-lead, by 2026-11-16 12:00 ET; its commit lands in the next stop and the baseline waits for it; a late commit never disqualifies AFL-016; not closed by 12:00 ET keeps the two-target route unchanged. (2) *Waves and fillers*: the per-`c` tables (rows `c` = 1, 3, 4, 5, 6, 10 and the two-target rows `c` = 1, 3, 5) replaced by one six-row table of the cases that can occur (baseline with 3 or 2 targets; official runs at `c` = 5 or 3 with 3 or 2 targets); general rule kept, stated for `n` counted trials (`n` = 6 or 4); the "When `c` > 6" sentence and the "Probe conditions" bullet on (d) picking sequential trials (`c` = 1) removed, since `c` is 5 or 3 under item (d)'s stated rule. No other rule changed.
- 2026-11-15 — developer: code ACs implemented in `harness/run_campaign.py`, `experiments/configs/main.yaml`, `src/fuzzer/fuzzer.py` (line buffering) with `tests/test_run_campaign.py`; run-time ACs (baseline, probe runs, pilots, freeze checklist, main campaign) not run and left unchecked. Gaps found: `targets/triggers.json` lacks the toy-1/toy-2 entries (AC "Trigger table" says this ticket adds them; outside the files this ticket pass could write); PyYAML is not installed, so the runner parses the flat YAML subset itself.
- 2026-11-15 — reviewer: BOUNCE. Blocking B1 (toy-1/toy-2 triggers absent; values verified), B2 (load_yaml dup keys/tabs/nan-inf silent), B3 (probe path and Hang-rule exit untested), B4 (Clean-tree (a) test lacks dirty==true run.json check), B5 (granularity_decision written on aborted pilot / overwritten), B6 (main accepts a config other than main.yaml, bypassing freeze diff); P1–P3 to lead. (reviewer, applied by developer)
- 2026-11-15 — developer: bounce fixes, back to review. B1 toy-1/toy-2 added to targets/triggers.json, symbolizer AC test now derives bugs from ground_truth.json and asserts the pilot proceeds (N1); B2 load_yaml refuses duplicate keys and tab indentation, _num refuses nan/inf, each naming the line, one test per case; B3 probe path tested through run() with a stubbed _launch (hang only in filler -> exit 1 and 'filler, not used'; no hangs -> exit 0; exec_per_s and hang_overhead columns from known values) plus probe_summary directly; B4 pilot run.json written by a CLI-like stub from a dirty tree, dirty == true asserted; B5 granularity_decision refused if present, never overwritten, written only for a completed pilot with a final row for every trial, else exit 1 naming the trials; B6 --kind main refuses any config but experiments/configs/main.yaml; N2 crash probe refuses commit unknown and records dirty; N4 target path must equal the launch path; N5 main refuses trials_per_config < 10 (AC 'Runs >=10 trials' ticked); N6 --dmax-json bad file/key is a clear refusal; N7 no empty PYTHONPATH entry. B6 and N5 do not apply to --crash-probe (not a campaign; the freeze checks skip it too). Not done, waiting on lead: N3, P2, P3, main.yaml placeholders, PyYAML, baseline detection, crash-probe overwrite. Gates: ruff clean, mypy src clean, pytest tests/test_run_campaign.py tests/test_fuzzer.py 115 passed. (developer)
- 2026-11-15 — reviewer: re-review APPROVE → testing. B1–B6 and N1, N2, N4–N7 are fixed; 17 mutants run in scratch copies: 15 caught, 2 survived (the B5 gaps below); 2 more not run (they would launch real runs) and reasoned instead. Two B5 test gaps survive mutation (aborted pilot whose trials all have final rows; half-written final_row): the tester adds both tests as a condition of the testing gate. Crash-probe exemption from B6/N5 endorsed. Gates: ruff and mypy clean; tests/test_run_campaign.py 75 passed (reviewer)
- 2026-11-15 — tester: added the two tests the reviewer made a condition of the testing gate, in tests/test_run_campaign.py: `test_aborted_pilot_with_all_final_rows_writes_no_decision` (concurrency-1 pilot, every stubbed trial writes a final row, the 6th returns exit 1: expect exit 1, 6 launches, no granularity_decision.json; kills `if ok and not missing` → `if not missing`) and `test_final_row_half_written_last_row_is_none` (full row then `10.5,12` gives None; kills removal of the half-row guard in `final_row`). Tests only, no source change (developer)
- 2026-11-15 — correction to the 2026-11-15 developer fix Log line on B2: the nan/inf refusal names the key and the value, not the line; only the tab and duplicate-key refusals name `path:line` (developer)
- 2026-11-15 — tester: PASS (code-checkable ACs), ticket stays in testing. The B5 re-review condition is met: both tests exist and each kills its mutant. Gates: ruff and mypy clean; pytest test_run_campaign/test_cli/test_fuzzer 142 passed, real-binary tests included. Seed sets for all six run kinds are disjoint (3 and 2 targets, c=1/3/5/10, 999 trials at base 0); the probe case table matches the pre-registration. 31 stubbed mutants: 30 caught, 1 benign survivor (sysctl exit-status, not isolated by test (e)). Open for the real run (user decision): 600 s budget, campaign-trial replay, the pilots and the ADR-0001 decision, retune/freeze run-time items, pre-freeze checklist (a)-(k), symbolizer pass per real run. Non-blocking T1-T4 in the Test section. No real probe, pilot, campaign or crash probe was run (tester)
- 2026-11-15 — AFL-016 cutoff met (AC "≥3 targets (PRD §8)", bullet "AFL-016 cutoff"): AFL-016 was moved to `tickets/done/` on 2026-11-15 at 08:33 ET (the file's creation time in `tickets/done/`; the crew-lead's DoD Log line there is dated 2026-11-15), before the 2026-11-16 12:00 ET cutoff. The campaign therefore runs on three targets, toy_parser, tlv_parser and the AFL-016 mini format parser, without `--allow-fewer-targets` (lead decision, 2026-11-15) (req-engineer)
- 2026-11-15 — lead decisions (lead decision, 2026-11-15) (req-engineer). New unticked ACs: "Baseline mode" (every probe trial and the crash-duration measurement at `c` = 1 whatever `main.yaml` says, labelled outputs, stubbed tests); "Abort stops running trials" (abort = the existing trial-failure/Clean-tree (b) abort, SIGINT/SIGTERM to the runner, or a fatal runner error; SIGTERM, then SIGKILL after 10 s; trials marked "aborted" in the campaign metadata; partial streams kept, never analysed; stub-target test); "Smoke run kind" (six trials at c = 5, `max_execs` 200, seeds `base_seed + 9000 + i`, `results/smoke/`, may run dirty, pass/fail only, excluded from analysis). New section "Known gaps": the one-restart limit (and "within the allowances left") is enforced by the operator, not the runner (T3). Loose ends from stop 1: item (k) no longer claims SIGFPE handling is unreliable (SIGSEGV/SIGBUS/SIGFPE all gave a full ASan stack); the smoke run added to "Seed sets disjoint" and, as a seventh set, to the "Seeds" bullet; item (i) and "Crash-duration measurement" *What runs* now say the baseline's crash-duration run is at 1 (the official runs at `c`). Checklist item (a) gains AFL-031 (stubbed ports of the tester's scratch tests, plus T2); evidence now six files. New tickets AFL-031 and AFL-032 in backlog
- 2026-11-15 (developer): run_campaign.py gains `--baseline` (probe and crash-probe forced to c = 1, labelled, own dirs `baseline` and `baseline_crash`, excluded from the floor). Abort now SIGTERMs then SIGKILLs every running trial's process group after `ABORT_GRACE_S` = 10 s, marks trials `aborted` in campaign.json, and exits non-zero. It triggers on a bad trial, runner SIGINT/SIGTERM, or an uncaught exception. `--kind smoke` (seed offset 9000, one trial per pair, `--max-execs 200`, `results/smoke/`, `excluded_from_analysis`, PASS/FAIL printed and recorded, dirty tree allowed). Tests added to tests/test_run_campaign.py. ruff, mypy and pytest pass.
- 2026-11-15 — reviewer: CHANGES REQUIRED on the three 2026-11-15 ACs (code matches the lead decisions; tests short of the ACs). B1 AC "Abort stops running trials": no test checks that the SIGTERM-ignoring stub dies only after the grace period, or that SIGTERM comes first; an in-memory mutant `abort_trials` = immediate SIGKILL, no grace, passes all 4 abort tests; trigger (2) has no ignoring variant and no partial-files check. B2 AC "Smoke run kind" test (a): the argv test runs 1 target at c = 3 (2 launches, `live["max"] <= 3` vacuous), not six launches at `main.yaml` c = 5; mutant "pool of 64 workers" survives. B3 AC "Baseline mode" (c): the label on the baseline crash_durations.json is not asserted (only `baseline: true`). Non-blocking: N1 abort/launch race SIGTERMs a just-launched trial but never SIGKILLs it; N2 `_ABORT.clear()` (execute) runs after the signal handlers are installed, so a signal in that window is recorded but trials run on; N3 baseline tests (b)/one-at-a-time not at concurrency 5, wrong "c x R per bug" comment. Text to update listed in the review report (Popen not `subprocess.run`, flag/paths, extra `--k`/`--dmax-json` refusals). campaign.json keys AFL-012 reads (`kind`, `excluded_from_analysis`, per-trial `aborted`, `aborted` list with `trial: null`, `targets`, `allow_fewer_targets`) are written as described. Gates: ruff clean, mypy src clean, tests/test_run_campaign.py 93 passed; abort/smoke/baseline subset 5 runs x 20 passed, no stub process left (reviewer)
- 2026-11-15 developer: bounce 1 fixed. B1 SIGTERM-handler stub with marker and grace-elapsed assert on all 3 abort triggers (+ partial metrics survive on signal); B2 smoke at c=5 with 3 targets: 6 launches, all 6 pairs, max live == 5; B3 baseline crash label asserted. N1 _launch SIGKILLs when abort already set (+test); N2 _ABORT.clear() moved before handler install; N3 comment fixed. Req-engineer items: crash measurement refuses a non-empty out dir (+test, baseline and not); exception handler records never-started trials as aborted+started:false (+multi-wave probe test); --baseline --dmax-json alone refusal test. Mutants (SIGKILL-at-once, 64-worker pool, dropped label) fail. ruff/mypy clean, 98 passed x5.
- 2026-11-15 developer: crash-measurement refusal narrowed to an existing crash_durations.csv/.json in the output dir (exit 2, nothing written), so the official default results/probe/<commit> still runs after baseline and baseline_crash; refusal test renamed (baseline on/off, pre-placed json); new sequence test (baseline probe, baseline crash, official crash, repeat refused); mutants (old broad check, check removed) fail the expected tests; ruff/mypy clean, 99 passed.
- 2026-11-15 — reviewer: re-review of bounce 1 APPROVE → testing (ticket stays in tickets/testing/). B1–B3 fixed: `check_term_then_kill` runs on all 3 abort triggers, trigger 2 uses `ignore,hang` and checks that partial metrics survive; the smoke test runs 3 targets at c = 5 (6 launches, 6 pairs, max live == 5); the baseline crash label is asserted. N1–N3 fixed. Req-engineer items: the exception path records never-started trials with `started: false`; `--baseline --dmax-json` is refused with a baseline message. The crash-measurement refusal is narrowed to an existing crash_durations.csv/.json, so the official default results/probe/<commit> runs after baseline and baseline_crash; the reviewer confirmed in memory that the earlier broad non-empty check refused that run. 10 in-memory mutants, all caught: SIGKILL at once, zero grace, N1 SIGTERM instead of SIGKILL, N1 branch removed, refusal removed, old broad refusal, `started: false` dropped, `--dmax-json` dropped from the baseline refusal, pool of 64 workers, baseline label dropped. The 0.8 × grace margin is not flaky: elapsed is measured from the SIGTERM marker to the assertion, after the SIGKILL at about 1.0 s, so load only makes it larger. Abort subset 5 runs × 12 passed, no stub process left. Notes, non-blocking: (1) the elapsed check measures time to the assertion, not to the stub's death; (2) crash_probe writes crash_durations.csv before its validity check, so after an invalid run a retry in the same directory is refused and needs `--out`. Text to update: the Baseline AC still says "non-empty output directory" / "non-empty `--out`"; the code refuses only an existing crash_durations.csv/.json. Gates: ruff clean, mypy src clean, tests/test_run_campaign.py 99 passed (reviewer)
- 2026-11-15 tester: PASS (baseline/abort/smoke ACs) — code matches the lead decisions (baseline c = 1 for probe and crash measurement; abort SIGTERM to each trial's process group, SIGKILL after ABORT_GRACE_S = 10 s in total, trials marked aborted; smoke six trials at main.yaml c, `--max-execs 200`, seeds base_seed + 9000 + i, results/smoke/, `excluded_from_analysis`, smoke in seed_sets/check_disjoint and caps). Gates: ruff (2 files) clean, mypy src clean, tests/test_run_campaign.py 99 passed; abort/smoke/baseline subset 3 × 27 passed; no stub_trial process left. Seed sets for the real main.yaml (base 1000, 3 targets, c = 5/3/1) disjoint, smoke = {10000}. aggregate.py excludes real stubbed smoke output by path, by `excluded_from_analysis` (also under `--out` elsewhere) and by kind. 24 in-memory mutants: 17 caught by the repo tests; 7 survive them, of which 6 are caught only by tester scratch tests (probe_summary.json baseline label dropped; `_dmax` baseline refusal removed, the repo test being masked by the dirty-tree refusal; os.kill instead of killpg; per-trial grace instead of total; culprit also marked aborted; smoke PASS without a final row) and 1 survives both (`--baseline` accepted with `--kind smoke`). Non-blocking defect: an exception raised after a trial was launched records that trial `{aborted: true, started: false}` although it ran (scratch test reproduces); analysis unaffected (aborted is excluded). Proposed follow-up tests and text fixes in the tester report. No real smoke run or fuzzing run (tester)
- 2026-11-15 — pre-freeze checklist item (l) added: first-pilot `no_stack` count per target and arm from each pilot trial's own crash_events.csv (runner or pilot evaluation step; not AFL-012), zero or option B reconsidered and decided before the freeze (AFL-030 contingency) (lead decision, 2026-11-15) (req-engineer)
- 2026-11-15 — ticket text aligned with the tester's findings (Baseline AC: concurrency wording, c=3/4 in the baseline tests, refusal for all kinds, smoke --out, baseline provenance, started:false known defect → AFL-031) (req-engineer)
- 2026-11-15 — previous Log line corrected: the c=3/4 wording fix was in the Baseline AC, not the abort tests (lead decision, 2026-11-15) (orchestrator)
- 2026-11-15 — experiments/configs/main.yaml `timeout_s` placeholder changed from 1.0 to 5.0, marked provisional for the probe phase: 5.0 s is the timeout the probe phase ran with (baseline and official run 1). Reason: crash reports went past 1 s under load in the tester's runs, and one crash recorded as a hang would trigger the hang rule and force the official runs to be repeated; a timeout only costs time when a run actually hangs. The final `timeout_s` is still k × D_max, set at the freeze (item (h)), and official run 2 runs at that final value (lead decision, 2026-11-15) (orchestrator)
- 2026-11-15 — until AFL-031 lands (probe and crash-probe refusal of a dirty tree), before any probe's numbers are used, check that `dirty` is false in that probe's metadata (`campaign.json` / `crash_durations.json`) and record the check in this Log (lead decision, 2026-11-15) (orchestrator)
- 2026-11-15 — **superseded: ReportCrash active.** The probe phase started early (AFL-016 cutoff already met) on 282f2ea, tree clean, after `make -C targets clean all` rc=0 (19:51:30Z, Homebrew clang): concurrency-1 baseline + baseline crash measurement, then official run 1 (`c` = 5) + crash measurement. Lower counted exec/s per target, baseline / official: toy_parser 18.3 / 10.7, tlv_parser 12.3 / 7.7, mini_format 14.0 / 10.8. The per-user crash reporter ran at up to ~80 % of a core while tlv_parser crashed (~3,300 crashes per trial), so (d) is not decided on these runs. Their official D_max, 0.280 s (tlv-1, `c` = 5, R = 5), still counts towards the timeout floor (lead decision, 2026-11-15) (orchestrator)
- 2026-11-15 — crash reporters off. (1) The user ran the per-user block (no sudo): `launchctl disable` + `bootout gui/501/com.apple.ReportCrash`, rc=0, service not found, `=> disabled`, no process; ~/Library/Logs/DiagnosticReports = 91 files. (2) **superseded: system crash reporter active.** The first rerun (`baseline_rcoff`, 21:24:44Z, rebuild rc=0) was stopped at 21:30:42Z by SIGTERM to the runner (abort handling: SIGTERM, SIGKILL after 10 s; all trials gone within 2 s): with the agent off, the system daemon `system/com.apple.ReportCrash.Root` (pid 51104) started at the first crash and wrote target reports to /Library/Logs/DiagnosticReports (75 -> 78). Its partial data (toy_parser uniform s3000, ~6 min) is kept and not used (lead decision, 2026-11-15, option 1). (3) The user ran the system block (sudo): `launchctl disable` + `bootout system/com.apple.ReportCrash.Root`, rc=0, service not found, `=> disabled`, no process; /Library count 78. **Both reporters off: the per-user agent and the system daemon.** (4) Functional test, 21:31:55–21:32:09Z: tlv-1's trigger (`015041424344`) 50 times through `fuzzer.executor.Executor` (targets/bin/tlv_parser, timeout_s 5.0): 50 runs, 50 crashes; `pgrep -x ReportCrash` every 0.2 s during and for 10 s after: nothing; report folders 91 -> 91 and 78 -> 78. PASS (lead decision, 2026-11-15) (orchestrator)
- 2026-11-15 — `baseline_rcoff2` (baseline: informs (d) and c, not used), 282f2ea, tree clean, `make -C targets clean all` rc=0, both reporters off, `c` = 1. Counted exec/s (uniform / fast): toy_parser 18.8 / 18.9, tlv_parser 14.4 / 14.4, mini_format 13.2 / 13.3; no hangs. Crash measurement (`c` = 1, R = 5): D_max 0.088 s (mfp-1), medians 0.073–0.078 s. Outputs results/probe/282f2ea…/baseline_rcoff2 and baseline_rcoff2_crash (orchestrator)
- 2026-11-15 — (d) at `c` = 5: `official1_rcoff2`, 282f2ea, both reporters off. Counted exec/s (uniform / fast): toy_parser 9.8 / 9.8, tlv_parser 8.2 / 8.4, mini_format 9.8 / 10.5 (fillers s3001 8.9–10.5, not used); no hangs. Rule (per target, lower counted exec/s over the two arms, official / baseline, within the reporters-off condition only): toy_parser 9.8 / 18.8 = 51.7 %, tlv_parser 8.2 / 14.4 = 56.8 %, mini_format 9.8 / 13.2 = 74.0 %; all below 80 %, so `c` = 3, once (commit dc54baf). Crash measurement (`c` = 5, R = 5): D_max 0.345 s (mfp-1); this run is superseded and its D_max counts towards the floor (lead decision, 2026-11-15) (orchestrator)
- 2026-11-15 — **official run 1** = `official1_rcoff_c3` (lead decision, 2026-11-15), dc54baf (282f2ea + `concurrency: 3`; same binaries, no rebuild), tree clean, both reporters off, `c` = 3, 2 waves, no fillers. Counted exec/s (uniform / fast): toy_parser 14.6 / 14.6, tlv_parser 14.4 / 14.2, mini_format 14.3 / 14.3; no hangs. (d) against `baseline_rcoff2`: toy_parser 14.6 / 18.8 = 77.5 %, tlv_parser 14.2 / 14.4 = 98.4 %, mini_format 14.3 / 13.2 = 108.3 %; toy_parser below 80 %, so `c` stays 3, disclosed in PRD §8 (vii). Crash measurement (`c` = 3, R = 5, 15 runs per bug): D_max 0.195 s (toy-2). k = 3. Floor over official runs, superseded included: max(0.280, 0.345, 0.195) = 0.345 s; 3 x 0.345 = 1.04 s; timeout_s = max(5.0, 1.04) = 5.0, so main.yaml's 5.0 is unchanged until item (h) at the freeze. Outputs results/probe/dc54baf…/official1_rcoff_c3 and official1_rcoff_c3_crash (orchestrator)
- 2026-11-15 — dirty checks (interim rule), read from each run's campaign.json, every trial's run.json and crash_durations.json, never from probe_summary.json: `baseline_rcoff2` 8 files, `official1_rcoff2` 12, `official1_rcoff_c3` 8; all `dirty = False` (orchestrator)
- 2026-11-15 — reporters-off evidence: `ps` sample every 180 s of ReportCrash and the analytics helpers: 27 samples over the rcoff2 runs and 7 over the `c` = 3 run, no ReportCrash in any (analyticsd at most 0.5 % CPU). Report-folder counts (~/Library / /Library): 91 / 78 at 21:32Z, 22:16Z (after the baseline's tlv_parser trials), 22:52Z (after the `c` = 5 tlv_parser trials), 23:54Z and 00:15Z (after the `c` = 3 run) (orchestrator)
- 2026-11-15 — load averages (1/5/15 min, `uptime`): baseline_rcoff2 start 2.33 / 2.43 / 3.80, end 4.62 / 4.49 / 4.22; official1_rcoff2 start 4.62 / 4.49 / 4.22, end 9.28 / 9.28 / 8.26; official1_rcoff_c3 start 1.50 / 1.46 / 1.55, end 5.64 / 5.13 / 4.13. Cores: hw.physicalcpu 10, hw.perflevel0.physicalcpu (performance) 4, hw.perflevel1.physicalcpu (efficiency) 6 (orchestrator)
- 2026-11-15 — stop 6: turn both crash reporters back on after the campaign: the per-user agent with `launchctl enable gui/$(id -u)/com.apple.ReportCrash` + `launchctl bootstrap gui/$(id -u) /System/Library/LaunchAgents/com.apple.ReportCrash.plist` (scratch script reportcrash-on.sh, no sudo); the system daemon with `sudo launchctl enable system/com.apple.ReportCrash.Root` + `sudo launchctl bootstrap system /System/Library/LaunchDaemons/com.apple.ReportCrash.Root.plist` (the commented lines at the end of reportcrash-root-off.sh) (lead decision, 2026-11-15) (orchestrator)
- 2026-11-15 — provenance of k (lead decision, 2026-11-15): k = 3 was fixed by the lead on 2026-11-15 before any probe numbers existed (recorded in the session; not timestamped in git). In git it is timestamped at d9a22db, before any pilot trial, which is what item (h) requires. (orchestrator)
- 2026-11-15 — process note: at stop 3 the git policy hook blocked one action, the orchestrator's Bash heredoc that wrote the commit message and the user's commit block, because the block's text contained the push command. The hook worked as intended; both files were rewritten with the Write tool, and the user ran the block (lead decision, 2026-11-15) (orchestrator)
- 2026-11-15 — first pilot run record: commit d9a22db, results/pilot/first_pilot, seeds base_seed + 1000 + i = 2000..2002, 3 trials per target x arm, c = 3, 00:31:33Z–01:31:36Z. Both macOS crash reporters off (launchctl print rc 113 for both; no ReportCrash process in 21 ps samples every 180 s); DiagnosticReports file counts 91 / 78 before and after; `make -C targets clean all` rc 0; runner rc 0; dirty False in campaign.json and all 18 run.json; tracked tree clean at start and end; load averages (1/5/15 min) start 2.53 / 2.30 / 2.76, end 4.26 / 4.49 / 4.42; the user's browser was among the top processes at the start (orchestrator)
- 2026-11-15 — first-pilot evaluation, retuning triggers per deep bug (found = a crash_events.csv row whose crash_site equals the bug's ground_truth function; first find = smallest elapsed_s; 5 % of 600 s = 30 s): toy-1 uniform 0/3, fast 1/3 (first find 569.2 s) -> (i) no, (ii) no; tlv-2 uniform 0/3, fast 0/3 -> (i) never found = yes, (ii) no; mfp-1 uniform 0/3, fast 0/3 -> (i) yes, (ii) no. tlv-2 and mfp-1 retune (AFL-035); toy-1 does not (orchestrator)
- 2026-11-15 — first-pilot evaluation, granularity trigger (final metrics.csv row, pooled over both arms, n = 6 per target; median distinct_path_ids / median corpus_size): toy_parser 4.5 / 3.5 fires (< 20); tlv_parser 14.0 / 8.0 fires (< 20); mini_format 65.5 / 20.0 does not fire. results/pilot/granularity_decision.json agrees: trigger_fired true, granularity "hit_count_buckets" (AFL-034) (orchestrator)
- 2026-11-15 — item (l): 0 rows with crash_site == "no_stack" for every target and arm (all 18 trials) (orchestrator)
- 2026-11-15 — item (g): toy-1 calibration prediction ("found in some trials but not all, in each arm"): uniform 0/3 = miss, reported as a miss as item (g) requires; fast 1/3 = met (orchestrator)
- 2026-11-15 — lead decisions after the first pilot: switch to hit-count buckets (AFL-034); retune tlv_parser and mini_format once each (AFL-035, target 1,500–3,000 expected mutants); AFL-031 in parallel; confirmation pilot on the stop-4 commit, seeds base_seed + 3000 + i, records numbers only and re-evaluates no rule (lead decision, 2026-11-15) (orchestrator)
- 2026-11-16 — confirmation pilot run record: commit 30d7e98, results/pilot/confirmation_pilot, seeds base_seed + 3000 + i = 4000..4002, 3 trials per target x arm, c = 3, 11:53:36Z–12:53:39Z. Both macOS crash reporters off (not loaded; no ReportCrash process in 21 ps samples every 180 s); DiagnosticReports file counts 91 / 78 before and after; `make -C targets clean all` rc 0; runner rc 0; dirty False in campaign.json and all 18 run.json; tracked tree clean at start and end; load averages (1/5/15 min) start 1.82 / 2.03 / 2.03, end 5.35 / 5.35 / 4.98. Not alone on the machine for most of the run: three leftover wait loops from the AFL-035 tester (each a `pgrep` every 10–15 s that matched its own shell and so never exited) were running at the start and were stopped during the run, before 12:53Z (orchestrator)
- 2026-11-16 — confirmation pilot numbers (records numbers only, re-evaluates no rule; lead decision, 2026-11-16). Deep-bug find rates per arm (found = a crash_events.csv row whose crash_site is the bug's ground_truth function; first find s): toy-1 uniform 1/3 (449.0), fast 0/3; tlv-2 uniform 0/3, fast 2/3 (191.2, 282.8); mfp-1 uniform 0/3, fast 0/3. Shallow bugs: toy-2, tlv-1, mfp-2 3/3 in both arms. Final metrics.csv row, median per arm (uniform / fast): distinct_path_ids toy 6 / 5, tlv 14 / 15, mfp 158 / 147; corpus_size toy 4 / 4, tlv 8 / 8, mfp 39 / 35; edges toy 8 / 8, tlv 13 / 13, mfp 45 / 45; hangs 0 in every trial. no_stack rows: 0 for every target and arm. exec/s per target, median of final-row execs / elapsed_s pooled over both arms (n = 6): toy_parser 14.6, tlv_parser 14.2, mini_format 14.4. Crash-file disk use (crashes/ dirs, du): toy 24 / 32 KiB, tlv 48 / 72 KiB, mfp 24 / 32 KiB (uniform / fast), 232 KiB in all (first pilot 224 KiB); whole run dir 3.7 MiB (orchestrator)
- 2026-11-16 — rule for item (h), fixed before any post-change official data (lead decision, 2026-11-16): official run 1 measured the code before the AFL-035 retune and the AFL-034 coverage switch, so official run 2 on the freeze candidate may diverge from it by more than 20% for that known reason. If the divergence check fails at the freeze, compare run 2's per-target exec/s with the confirmation pilot's (above; also the new code at c = 3). If they agree within 20%, the cause is the planned code change and run 2's values are used; the D_max floor still takes the largest over every official run. If they do not agree, stop and report to the lead (orchestrator)
- 2026-11-16 — lead decisions on the stop-4 items: (a) AFL-036 before the freeze (Opus drafting): PRD deviation (iv) and the §8 coverage wording to hit-count buckets, dated superseded notes in ADR-0004 §2 and ADR-0005 §6, and a correction Log line for AFL-034's incorrect Makefile claim; (b)+(i) AFL-037 before the freeze (Sonnet dev, Opus review): the five AFL-031 fixes and a tlv fixture header-sha test; AFL-036 and AFL-037 added to pre-freeze checklist item (a); (c) accepted, noted in AFL-036's Log; (d) crash-file disk use measured in the confirmation pilot (above); (e) covered by (a); (f) AFL-035 mechanism differs from the decision's wording (S0 moved instead of the comparisons; one line added to tlv_parser.c); accepted by the lead; (g) the five AFL-035 disclosures go into AFL-024's threats to validity; (h) the rule above; (j) accepted (lead decision, 2026-11-16) (orchestrator)
- 2026-11-16 — crash-reporter `disabled` field (AFL-037, recorded here because AFL-037 is closed; lead decision, 2026-11-16): an unlisted label gives false, accepted. In campaign.json and crash_durations.json, `disabled: false` means no disabled override is set in launchd's database for that label; null means the state is unknown (command failed or token not recognised). (orchestrator)
- 2026-11-16 — confirmation-pilot lesson (lead decision, 2026-11-16): the AFL-035 retune target (an expected 1,500–3,000 mutants of the staircase seed) did not account for round-robin splitting each trial's budget across the corpus; this is the lead's calibration error. mini_format's final corpus was about 37 seeds (median corpus_size 39 uniform / 35 fast), so mfp-1's effective cost is far above the per-trial budget (arithmetic, not measured: about 14.4 exec/s x 600 s = about 8,600 executions per pilot trial, about 230 per seed over 37 seeds, against a staircase sum of about 1,978), and mfp-1 was never found. No second retune is allowed, so mfp-1 stays as is and its time-to-find endpoint is expected to be mostly censored. Disclosed in AFL-024's threats, not fixed. (orchestrator)
- 2026-11-16 — standing rule, process hygiene before every timed run (official run 2 and the main campaign; lead decision, 2026-11-16): before starting, list and stop every stray agent or test process (pytest, pgrep wait loops, leftover shells); record the top processes at start and at end of the run. Reason: the confirmation pilot ran alongside three stray wait loops. (orchestrator)
- 2026-11-16 — freeze sequence on the candidate freeze commit 1aa932fc57d585104f94aa2c92ff116a94387f58 (1aa932f), started 2026-11-16T15:05:47Z, tracked tree clean at start and at end; the entries below are its evidence (lead decision, 2026-11-16) (req-engineer)
- 2026-11-16 — hygiene before the run (standing rule above; 2026-11-16T15:05:47Z, 1aa932f): no stray agent, test or wait process; the per-user and the system ReportCrash both not loaded (`com.apple.ReportCrash` => disabled); DiagnosticReports file counts user 91 / system 78 at start and 91 / 78 at end (15:40:36Z); `hw.physicalcpu` 10. Top snapshot at start (15:05:47Z): load average 2.23 / 2.17 / 2.13, CPU 6.13 % user, 13.18 % sys, 80.67 % idle; its process list, sorted by PID, shows 0.0 % for every listed process. Load and top CPU users at the official-run-2 points: at the first trial (15:20:30Z) load 2.51 / 2.91 / 2.69, top fseventsd 101.1 %, WindowServer 18.5 %, mds_stores 18.2 %, a Brave Browser renderer 17.8 %, mds 13.9 %; at the end of the trials (15:40:31Z) load 5.85 / 5.48 / 4.76, top a Brave Browser renderer 45.5 %, WindowServer 41.1 %, a Brave Browser helper 26.8 %, Brave Browser 13.6 %, cameracaptured 11.9 %; at the end of the crash measurement (15:40:35Z) load 5.85 / 5.48 / 4.76, top opendirectoryd 61.3 %, tccd 38.9 %, WindowServer 33.8 %, a Brave Browser helper 24.1 %, a Brave Browser renderer 20.0 %. Top snapshot at end (15:40:35Z): load average 5.85 / 5.48 / 4.76, CPU 10.13 % user, 13.82 % sys, 76.3 % idle. (req-engineer)
- 2026-11-16 — ReportCrash sampling, `ps` every 180 s from 15:05:48Z to 15:38:48Z, 12 samples: no ReportCrash process in any sample. The processes listed were SubmitDiagInfo, audioanalyticsd, analyticsd and osanalyticshelper; analyticsd was at most 0.3 % CPU, the others 0.0 %. Report-folder counts stayed 91 / 78 from start to end (req-engineer)
- 2026-11-16 — item (f): `make -C targets clean all` rc 0 on 1aa932f at 2026-11-16T15:05:49Z (req-engineer)
- 2026-11-16 — item (b): `pytest -m slow` on 1aa932f, rc 0, "10 passed, 590 deselected in 877.24s (0:14:37)" (finished 15:20:29Z), run against the committed S0s. `--collect-only -q` selection by file: tests/test_toy_parser.py 1, tests/test_tlv_parser.py 1, tests/test_mini_format.py 1 (the depth sweeps, one per experiment target), tests/test_fuzzer.py 1, tests/test_retune_odds.py 6; 10 in all. The individual test ids are not in the captured output, only these per-file counts (req-engineer)
- 2026-11-16 — item (k) on 1aa932f, three pieces of evidence (req-engineer). (i) AFL-030 static test, `pytest tests/test_target_static_check.py` rc 0: 25 passed in 0.54s. (ii) Crash-duration measurement Validity rule: 90 rows, 0 invalid; every row `outcome == "crash"`, signal 6, `crash_site` equal to the bug's ground_truth function. (iii) Per-target review (reviewer, 2026-11-16): no `/` or `%` arithmetic on any planted bug's path, and none anywhere in the code of toy_parser.c, tlv_parser.c or mini_format.c (only comment delimiters and the `%u` format string at tlv_parser.c:76). Paths: toy-1 main -> check; toy-2 main -> check -> scan; tlv-1 main (memcpy); tlv-2 main -> parse_ext; mfp-1 main -> rec_table -> rec_get; mfp-2 main -> rec_data. The mfp handlers that may run before them (rec_pairs, rec_skip and the others) also contain none. OPEN POINT for the lead, not a decision: targets/cov_rt.c:40 has `next_id++ % MAP_SIZE` in the guard-init hook, with the constant nonzero divisor 65536. It is shared instrumentation, not a target; the reviewer reads it as outside (k). libc and ASan internals were not reviewed
- 2026-11-16 — **official run 2** = `official2` (lead decision, 2026-11-16), 1aa932f, tree clean, both reporters off, `--kind probe --run-name official2`, `c` = 3, `timeout_s` 5.0, 2 waves, 6 counted trials, no fillers, seeds `base_seed + 2000 + i` = 3000, 2026-11-16T15:20:30Z–15:40:31Z, rc 0; `dirty` False on every record. Outputs results/probe/1aa932fc57d585104f94aa2c92ff116a94387f58/official2/probe_summary.json and the crash measurement beside it (crash probe rc 0, finished 15:40:35Z). Counted exec/s (uniform / fast): toy_parser 14.05 / 14.05, tlv_parser 13.77 / 13.24, mini_format 13.56 / 13.56; no hangs. Per-trial table, both official runs (run 1 = `official1_rcoff_c3`, dc54baf), every trial counted, seed 3000, hangs 0, hang rate 0.0, hang_time_s 0.0, overhead 0.0 in every row:
  | run | target | schedule | wave | exec/s | execs |
  |---|---|---|---|---|---|
  | 1 | toy_parser | uniform | 0 | 14.61 | 8765 |
  | 1 | toy_parser | fast | 0 | 14.60 | 8763 |
  | 1 | tlv_parser | uniform | 0 | 14.38 | 8629 |
  | 1 | tlv_parser | fast | 1 | 14.16 | 8497 |
  | 1 | mini_format | uniform | 1 | 14.31 | 8587 |
  | 1 | mini_format | fast | 1 | 14.31 | 8587 |
  | 2 | toy_parser | uniform | 0 | 14.05 | 8432 |
  | 2 | toy_parser | fast | 0 | 14.05 | 8432 |
  | 2 | tlv_parser | uniform | 0 | 13.77 | 8261 |
  | 2 | tlv_parser | fast | 1 | 13.24 | 7943 |
  | 2 | mini_format | uniform | 1 | 13.56 | 8138 |
  | 2 | mini_format | fast | 1 | 13.56 | 8138 |

  Hang rule: `hang_rule_violated` False for both runs; 0 hangs in every trial of both runs, counted or filler (no fillers). (req-engineer)
- 2026-11-16 — crash-duration measurement on 1aa932f (`official2`, `c` = 3, R = 5, `probe_timeout_s` 30.0, 15 runs per bug, `dirty` False, `hw.physicalcpu` 10), per bug median / max in seconds: toy-1 0.098 / 0.112; toy-2 0.099 / 0.108; tlv-1 0.099 / 0.123; tlv-2 0.100 / 0.118; mfp-1 0.100 / 0.163; mfp-2 0.101 / 0.143. D_max 0.163 s (mfp-1) (req-engineer)
- 2026-11-16 — divergence check, run 1 vs run 2, exec/s per counted (target, schedule), |a - b| / max(a, b), threshold 0.20: mini_format fast 14.31 / 13.56 = 0.052; mini_format uniform 14.31 / 13.56 = 0.052; tlv_parser fast 14.16 / 13.24 = 0.065; tlv_parser uniform 14.38 / 13.77 = 0.043; toy_parser fast 14.60 / 14.05 = 0.038; toy_parser uniform 14.61 / 14.05 = 0.038; D_max 0.195 (toy-2) / 0.163 (mfp-1) = 0.161. All pass; the divergence check passes. The 2026-11-16 item (h) fallback (comparison with the confirmation pilot) was therefore not needed (req-engineer)
- 2026-11-16 — conservative values per target (counted trials, both schedules, both official runs; lower exec/s, higher hang count): toy_parser exec/s 14.05 (run 2, fast), hangs 0; tlv_parser exec/s 13.24 (run 2, fast), hangs 0; mini_format exec/s 13.56 (run 2, uniform and fast), hangs 0. Run 1's lower values were 14.60, 14.16 and 14.31 (req-engineer)
- 2026-11-16 — item (h) floor over all official runs, superseded included, baseline excluded: `official1` (282f2ea, `c` = 5, ReportCrash on) 0.280 s; `official1_rcoff2` (282f2ea, `c` = 5) 0.345 s; official run 1 (dc54baf, `c` = 3) 0.195 s; official run 2 (1aa932f, `c` = 3) 0.163 s. Max D_max 0.345 s; k = 3, so k x max = 1.036 s <= `timeout_s` 5.0 s. The floor holds, `timeout_s` 5.0 stays unchanged and is the final value (req-engineer)
- 2026-11-16 — closing: this is evidence on the candidate freeze commit 1aa932f. The freeze hash is not recorded until item (b) passes on the freeze commit itself (req-engineer)
- 2026-11-16 — lead rulings on the freeze package (lead decision, 2026-11-16). (j): the "D_max before the first pilot" blank is 0.195 s (toy-2, official run 1); the added floor sentence with the superseded 0.345 s, the wording "on the candidate freeze commit 1aa932f" and the note "the higher of its two schedules' counted trials" are kept. (vii): the causal clause is reworded to "attributed to executor overhead (a new process per run plus ASan start-up); not profiled separately", because no measurement splits the per-execution time. experiments/configs/main.yaml is left byte-identical to the commit official run 2 ran on; its "provisional" comment is stale, and `timeout_s` 5.0 is final under item (h). The freeze AC and ADR-0005 §4 are unchanged before the freeze. (k): the `% MAP_SIZE` at targets/cov_rt.c:40 is out of scope for (k), because it is instrumentation with a constant divisor; this closes the open point above. Item (j) evidence: the lead read the PRD §8 text on 2026-11-16, before the freeze commit (orchestrator)
- 2026-11-16 — ordering: 1679c36 (PRD §8 (j) and (vii), freeze-sequence evidence) was committed and pushed before the (vii) ruling was applied; the commit that adds this line applies it and is the freeze commit, the last commit before the main campaign. Its targets/, experiments/, src/, harness/ and tests/ are identical to 1aa932f, the commit official run 2 ran on. (f) and (b) are rerun on it before the campaign starts. The freeze hash is recorded after the campaign, as the 2026-11-16 lead procedure sets out (orchestrator)
- 2026-11-17 — freeze hash: `ff19bef7abb57b1ccbffd0318e2bbcb3c13f9cfc`. The freeze commit was pushed at 2026-11-16T18:52:14Z, before the campaign's first started_at 2026-11-16T19:06:36Z. Procedural change (lead decision, 2026-11-16): the hash is recorded after the campaign, and the campaign's `--freeze-commit` was the pushed HEAD, checked equal to HEAD and to origin/main at the start, instead of a hash copied from a pre-campaign Log entry (Freeze bullet; Clean-tree provenance (c); 2026-11-07 decision). Pre-freeze check (b) on ff19bef: `pytest -m slow` rc 0, 10 passed, 590 deselected in 840.59s, finished 2026-11-16T19:06:35Z; it selected `test_single_byte_sweep` in tests/test_toy_parser.py, tests/test_tlv_parser.py and tests/test_mini_format.py, plus 1 slow test in tests/test_fuzzer.py and 6 in tests/test_retune_odds.py. Pre-run check (f) on ff19bef: `make -C targets clean all` rc 0, 2026-11-16T18:52:31Z (orchestrator)
- 2026-11-17 — main campaign run record: commit ff19bef (the freeze commit), results/main, `--kind main`, seeds base_seed + i = 1000..1009, 10 trials per target x arm, 60 trials, `c` = 3, `timeout_s` 5.0, 2026-11-16T19:06:36Z–22:26:41Z, runner rc 0, `aborted` None. All 60 trials returncode 0 and counted; elapsed 600.001–600.070 s; hangs 0. exec/s medians (uniform / fast): toy_parser 14.38 / 14.38, tlv_parser 14.21 / 14.16, mini_format 14.36 / 14.36. Both macOS crash reporters off (not loaded and disabled at start and end in campaign.json; no ReportCrash process in 72 ps samples every 180 s); DiagnosticReports file counts 91 / 78 before and after; `dirty` False in campaign.json and all 60 run.json, `freeze_commit` ff19bef in each; tracked tree clean at start and end; no sleep (sample gaps 180–181 s; power log has no sleep or wake events in the window); load averages (1/5/15 min) start 2.13 / 2.01 / 2.23, end 4.68 / 4.43 / 4.46 (orchestrator)
- 2026-11-17 — analysis: harness/aggregate.py and harness/plots.py (ff19bef plus AFL-033) run once each on results/ at 2026-11-17T00:50:55Z and 00:50:57Z, rc 0; outputs copied unmodified to docs/report/, with the file hashes and commands in docs/report/PROVENANCE.md. H1 by the PRD §8 rule: not supported (no primary member with Holm p < 0.05; every p_holm 1; smallest raw p 0.5129). Accepted as final; nothing was re-run or changed after the numbers (lead decision, 2026-11-17). Raw results are kept off the repository; data/SHA256SUMS lists every raw file and the archive (lead decision, 2026-11-17, option 1) (orchestrator)
