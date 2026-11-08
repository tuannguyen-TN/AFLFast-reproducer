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
- [ ] Re-running a trial with the same seed and the same `max_execs` stop reproduces
      its exec-indexed metrics and crash-event streams exactly, in every column
      except wall-clock fields (`elapsed_s`), per AFL-007 / ADR-0005 (replay on the
      exec index; timeouts are the one disclosed timing-dependent exception). A
      trial stopped by the wall-clock budget is not required to replay beyond the
      exec index it reached.
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
      - `src/fuzzer/mutator.py` is unchanged by this check (`git diff` on it is
        empty).
      - The statement "non-empty S0 + no operator empties a non-empty input ⇒
        `mutate(b"")` is unreachable in a campaign" is recorded in a code comment
        next to the length check, citing AFL-011 (and AFL-019 as its origin).
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
- 2026-11-07 — batch grooming: reproducibility AC reworded to exec-index replay (AFL-007 / ADR-0005); AFL-019's ACs folded into the S0 pre-flight AC block (zero-length S0 rejected, test, mutator.py unchanged, reachability comment) (human decision) (req-engineer)
- 2026-11-07 — review fix: added "Clean-tree provenance" AC: (a) main campaign aborts on a dirty tree (tracked changes only), no override, pilots may run dirty and record it; (b) one commit per campaign, every main trial's run.json has the start commit and dirty == false, else abort and flag; (c) `git diff --quiet <freeze_commit> HEAD -- targets/ experiments/configs/main.yaml` must pass, no override, freeze_commit = hash logged at freeze time; (d) output under results/, nothing written is tracked; .gitignore covers results/ only for *.json/*.png/*.csv (human decision) (req-engineer)
- 2026-11-07 — review fix: freeze hash supplied via required `--freeze-commit HASH` (copied from the freeze Log entry; not main.yaml, which would fail its own diff check; not a tag, which is mutable); added (c.i) `git merge-base --is-ancestor` check aborting loudly and (c.ii) full 40-char `freeze_commit` in every trial's run.json, each with a test (human decision) (req-engineer)
- 2026-11-07 — review fix: (c.i) now calls AFL-008's shared `resolve_freeze_commit` helper once at campaign start, before any trial (no runner-side freeze check, grep test); (c.ii) runner passes the resolved hash to each trial's CLI via `--freeze-commit`, CLI stays run.json's single writer; (d) stale `.gitignore` fact removed, points to AFL-015 (human decision) (req-engineer)
