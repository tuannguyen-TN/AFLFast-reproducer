---
id: AFL-011
title: Campaign runner — N trials × targets × schedules (Klees backbone)
requirement: FR-7
paper_ref: Klees §methodology (repeated trials, fixed budget, seeds)
module: harness/run_campaign.py
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
- [ ] Each trial honours `seconds_per_trial` and writes a per-trial metrics file
      (edges-over-time, unique-crashes-over-time, time-to-first-crash).
- [ ] Each result records commit hash + exact command (NFR-1).
- [ ] Re-running a trial with the same seed reproduces its metrics stream.
- [ ] Per-trial metrics also record `distinct_path_ids` (count of distinct
      `coverage.path_id` values over all execs) and `corpus_size`, both final and
      over time.
- [ ] **Pilot + coverage-granularity fallback (pre-registered, ADR-0001).** A pilot
      mode runs 3 trials per (target × schedule) at the main `seconds_per_trial`, with
      seeds `base_seed + 1000 + i` (disjoint from main trials), writing to
      `results/pilot/`; pilot results are excluded from AFL-012 analysis. Decision
      rule, evaluated on the pilot before the main campaign, pooled over both arms,
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
      - **When evaluated.** On the first pilot only.
      - **Seeds.** The first pilot, the confirmation pilot and the main campaign
        each use fresh trial RNG seeds, pairwise disjoint: no seed is reused
        across any two of them. All seeds are recorded.
      - **Trigger (two-sided, per deep bug).** (i) *Never found:* neither arm finds
        the bug in any first-pilot trial. (ii) *Trivially found:* both arms find
        the bug in every first-pilot trial within the first 5 % of
        `seconds_per_trial`. If either condition holds, that bug's target may be
        retuned.
      - **Limit.** A target is retuned at most once. This rule and the
        coverage-granularity fallback above are each evaluated exactly once, in
        total, on the first pilot, and each fires at most once.
      - **After a retune.** Every AC of the target's ticket still passes. The
        change is logged in that target ticket's Log, with the first-pilot
        numbers that triggered it.
      - **Confirmation pilot.** If any target was retuned or the granularity
        changed, one confirmation pilot runs after all changes are applied, using
        the same pilot procedure. Its results are recorded in
        `results/pilot/` and reported. It is never used to re-evaluate or
        re-trigger either rule, even when its numbers would meet a trigger. If
        nothing changed, no confirmation pilot runs.
      - **Freeze.** Before the main campaign, the targets and
        `experiments/configs/main.yaml` are frozen at a commit. Its hash is
        recorded in this ticket's Log and in each target ticket's Log (AFL-009,
        AFL-010, AFL-016). After the freeze, no target or threshold changes. The
        thresholds in this AC and in the granularity fallback cannot be edited
        once any pilot data exists.
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
- [ ] **Initial corpus = S0 (human decision, 2026-11-07; PRD §8).** In
      `experiments/configs/main.yaml`, each target's initial corpus is exactly the
      directory `targets/seeds/<target>/` (`<target>` = binary name), which
      contains only `S0` (AFL-009/010/016). It is passed to every trial via the
      CLI's `--seeds DIR` (AFL-008) and is identical in both arms. The runner
      records the seed directory path and the SHA-256 of each file in it in the
      campaign metadata. Test: the recorded corpus is the same for every UNIFORM
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

## Technical notes (architect)
Harness depends on the fuzzer package, never the reverse. Keep statistics OUT of
this file (that is AFL-012); here only orchestrate + persist raw metrics.
The pilot rule is a fixed threshold on two medians, not a statistic, so it stays here.
`distinct_path_ids` has to come from the fuzzer loop's metrics (AFL-007): it keeps a
set of `path_id`s seen. Under presence-only every retained seed has a unique path, so
"distinct paths ≈ corpus size" means f(i) barely exceeds the seed's own fuzzing and
FAST cannot separate rare from frequent paths. That is what the trigger detects.
Granularity is never an arm-level knob: both arms always share it (NFR-2).

## Test approach (tester)
Validity checklist: trial count, distinct seeds, budget honoured, reproducibility
under fixed seed. Flag any Klees anti-pattern (single-run, missing variance).

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
