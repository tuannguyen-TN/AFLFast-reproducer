---
id: AFL-011
title: Campaign runner — N trials × targets × schedules (Klees backbone)
requirement: FR-7
paper_ref: Klees §methodology (repeated trials, fixed budget, seeds)
module: harness/run_campaign.py, experiments/configs/main.yaml (timeout_s, concurrency), src/fuzzer/fuzzer.py (CSV line buffering only)
depends_on: [AFL-007, AFL-009, AFL-010, AFL-016]
status: backlog
owner: developer
---

## Goal
Run the comparison the way Klees requires: many independent trials per condition,
fixed wall-clock budget, distinct recorded seeds, persisted time-series metrics.

## Acceptance criteria
- [ ] Reads `experiments/configs/main.yaml`.
- [ ] Runs ≥10 trials per (target × schedule); trial i uses `base_seed + i`.
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
- [ ] **Seed sets disjoint, checked at campaign start (human decision,
      2026-11-13).** At the start of every campaign (main, any pilot, or a
      probe run), before any trial, the runner builds the full seed set of
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
- [ ] **Partial streams survive an external kill (human decision, 2026-11-13).**
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
        2026-11-14).
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
      - [ ] (a) AFL-015, AFL-018, AFL-027, AFL-028 and AFL-030 (AFL-030 added,
        human decision, 2026-11-14) are in `tickets/done/`.
        Evidence: `ls tickets/done/` output that lists all five ticket files.
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
        is the concurrency of the crash-duration measurement, and it is
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
        integer divide by zero (on macOS/arm64 `sdiv` does not trap, and
        SIGFPE handling is unreliable); and every campaign target's source
        passes AFL-030's AC "Strict static source check", which holds the list
        of banned forms (kept there only, not copied here). Evidence: the
        crash-duration measurement's run on the candidate freeze commit passing
        its *Validity* rule (every row `outcome == "crash"`, signal 6,
        `crash_site` equal to the bug's `function`); AFL-030's static test's
        pytest pass summary on that commit; and, per campaign target, a review
        that no planted bug's path contains `/` or `%` arithmetic (as AFL-010's
        "Two planted bugs" AC requires), with the commit it was done on.
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
          planned concurrency) run in parallel; each runs every trigger once per
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
- [ ] **Campaign timeout and concurrency from the config (human decision,
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
- [ ] **Campaign machine recorded (human decision, 2026-11-13).** The campaign
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
- [ ] **≥3 targets (PRD §8).** `experiments/configs/main.yaml` lists ≥3 distinct
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
- [ ] **Initial corpus = S0 (human decision, 2026-11-07; PRD §8).** In
      `experiments/configs/main.yaml`, each target's initial corpus is exactly the
      directory `targets/seeds/<target>/` (`<target>` = binary name), which
      contains only `S0` (AFL-009/010/016). It is passed to every trial via the
      CLI's `--seeds DIR` (AFL-008) and is identical in both arms. The runner
      records the seed directory path and the SHA-256 of each seed file in it
      (non-hidden regular files, AFL-007 AC "Seed files and load order"; i.e. S0)
      in the campaign metadata. Test: the recorded corpus is the same for every UNIFORM
      and FAST trial of a target.
- [ ] **Pre-flight S0 integrity check (human decision, 2026-11-07).** Before any
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
- [ ] **Clean-tree provenance (human decision, 2026-11-07).** "Dirty" means
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

## Test approach (tester)
Validity checklist: trial count, distinct seeds, budget honoured, reproducibility
under fixed seed. Flag any Klees anti-pattern (single-run, missing variance).
Before the freeze: confirm the freeze Log entry records a passing `pytest -m slow`
on the freeze commit itself, with at least one depth sweep per target selected.

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
