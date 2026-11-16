---
id: AFL-035
title: Retune tlv_parser (tlv-2) and mini_format (mfp-1) staircases, once each
requirement: FR-7 / AFL-011 AC "Pre-registered target retuning rule and freeze"
paper_ref: AFLFast §3.2 (staircase) / Klees (target choice)
module: targets/tlv_parser.c, targets/mini_format.c, targets/triggers.json, targets/seeds/ (S0 + SHA256SUMS, S0 changed), tests/test_tlv_parser.py, tests/test_mini_format.py, tests/test_retune_odds.py (`@pytest.mark.slow`, fixed RNG seed), tests/fixtures/tlv_parser_asan_memcpy.txt (AFL-007 fixture, re-captured)
depends_on: [AFL-010, AFL-016, AFL-011, AFL-034]
status: done                               # backlog|in-progress|review|testing|done
owner: tester
---

## Goal
The deep bugs tlv-2 (tlv_parser) and mfp-1 (mini_format) were never found in the
first pilot, so the pre-registered retuning rule fires. Retune each target once so
every staircase step is reachable by the real `mutate()`. Data-affecting: **Opus
review**.

First-pilot numbers that triggered the retune (run on d9a22db,
results/pilot/first_pilot, seeds 2000..2002, 3 trials per target x arm, c = 3;
found = a crash_events.csv row whose crash_site equals the bug's ground_truth
function; first find = smallest elapsed_s; 5 % of 600 s = 30 s): tlv-2 uniform
0/3, fast 0/3 -> (i) never found = yes, (ii) no. mfp-1 uniform 0/3, fast 0/3 ->
(i) yes, (ii) no. toy_parser is not retuned (toy-1 uniform 0/3, fast 1/3, first
find 569.2 s: neither trigger).

Lead decision (2026-11-15): keep unchanged each bug's function, bug class and
crash site (so ground_truth.json names are unchanged), the shallow bugs, and the
definition of deep (no single-byte substitution of S0 reaches it, and a staircase
of at least 3 steps, each clean and each adding an edge). Change the staircase's
comparisons so each step is reachable by the real `mutate()`. Calibrate: measure
each step's odds with the real mutator (200,000 mutants per step, as the AFL-009
reviewer did for toy-1). Target an expected total (the sum of 1/p) of 1,500-3,000
mutants from S0. That is easier than toy-1 (about 10,750) because hit-count
buckets (AFL-034) grow the corpus and spread energy thinner, and it is far from
"trivially found" in 30 s (about 430 executions). If S0 changes, update
triggers.json and SHA256SUMS in the same change.

## Acceptance criteria
- [x] Unchanged identity: tlv-2 stays in `parse_ext` and mfp-1 in `rec_get`; bug class and crash site unchanged; `ground_truth.json` unchanged (verified by diff).
- [x] Shallow bugs tlv-1 and mfp-2 unchanged in function, bug class and crash site; their `triggers.json` entries are the new S0's single substitutions (lead decision 2026-11-15: if S0 changes, update triggers.json in the same change) and each crashes at its function.
- [x] Deep holds for each retuned bug: no single-byte substitution of S0 crashes at the bug's function; a documented staircase S0 -> ... -> Sk with k >= 3, each step clean (no crash) and adding at least one new edge, measured via `Executor`.
- [x] Odds measured: each step's odds p measured with the real `mutate()`, 200,000 mutants per step, fixed RNG seed, one reproducible command (`@pytest.mark.slow` test or script under tests/); the numbers are recorded in this ticket's Log.
- [x] Calibration: for each retuned bug, the sum of 1/p over the steps from S0 lies in [1,500, 3,000].
- [x] `targets/triggers.json` entries for tlv-2 and mfp-1 are updated to the new staircase ends (and reproduce the crash at the bug's function).
- [x] If S0 changes, `targets/seeds/` S0 and `SHA256SUMS` are updated in the same change; if S0 does not change, neither is touched.
- [x] AFL-030's static source check passes on both retuned sources.
- [x] Every AC of AFL-010 and AFL-016 still passes, including the slow depth sweeps (`pytest -m slow`).
- [x] Retune log: the first-pilot numbers above are appended as one Log line each to AFL-010's and AFL-016's Logs (see Technical notes).
- [x] Limit: each target is retuned at most once; toy_parser is not touched.
- [x] `ruff check .`, `mypy src` and `pytest` pass.

## Technical notes (architect)
- Rule text: AFL-011 AC "Pre-registered target retuning rule and freeze" (Trigger, Limit, After a retune, Confirmation pilot). Depth definitions: AFL-016 "Depth definitions". Odds method precedent: AFL-009 Log (reviewer's per-step measurement with the real `mutate()`, 200,000 mutants per step).
- Appending to `tickets/done/AFL-010*` and `tickets/done/AFL-016*` Logs is required by the retuning rule's "After a retune" bullet (lead decision, 2026-11-15) and is the only change allowed to those closed tickets.
- Depends on AFL-034 because the calibration target assumes hit-count-bucket coverage; measure odds on the AFL-034 build.
- Static source rules (AFL-030) apply; rebuild with `make -C targets clean all`.
- The confirmation pilot (seeds base_seed + 3000 + i, on the stop-4 commit, same run conditions) follows this ticket; it records numbers only and re-evaluates no rule (lead decision, 2026-11-15). It is not part of this ticket.
- Data-affecting: Opus review.

## Test approach (tester)
Re-run the odds measurement independently with a different fixed seed and check each p within sampling error; confirm no single-byte substitution of S0 reaches the bug; run `pytest -m slow`; diff ground_truth.json and the shallow-bug entries.

## Re-review (reviewer, 2026-11-15) — APPROVED

Bounce-1 fixes, each checked against the diff and a fresh scratch build (`make -C targets clean all`):
- Must-fix 1 (trigger table): pass. triggers.json tlv-1 = 015041424344fe025900 and mfp-2 = 4d46010041057879abff470042016b76, each the new S0 with one byte substituted. `== T1` (test_tlv_parser.py:65) and `== T2` (test_mini_format.py:88) are restored. AC 2 is reworded per the lead decision. The Log records that AFL-010 AC 3's literal is superseded. tlv-2 and mfp-1 are unchanged, toy entries unchanged, ground_truth.json unchanged (git diff empty).
- Must-fix 2 (tlv_parser.c header): pass. T1 and the guard-side inputs are 10-byte S0 forms, "(= S0)" is now true, and there are no line numbers. mini_format.c gains the T2 literal. Code is still the single `ext-index-oob` line; no comparison changed.
- Must-fix 3 (AFL-007 fixture): pass. sha256 of targets/tlv_parser.c = a3c01b3c...a99e, which equals the fixture header. A fresh scratch build run on the tlv-1 trigger gives the same ERROR, WRITE size 80, frames `main tlv_parser.c:75` and `:62`, and SUMMARY as the fixture (addresses and PIDs normalised). The fixture is in the module list. Finding, outside this ticket's ACs: no test reads the header sha. test_fixture_not_stale compares only the crash_site function ("main"), so a future tlv_parser.c edit that moves lines would break no test. This gap comes from AFL-007, not AFL-035. A one-line test (fixture header sha256 == sha256(targets/tlv_parser.c)) would close it; recommended as a follow-up before the AFL-011 freeze. Until then the only guard is the Log note "must not be edited again without re-capturing".
- S1, S2: disclosed in the Log with the reviewer's numbers. pass.
- S3: near-miss sampling was added to test_predicate_matches_executor_edges. It asserts len(near) > 0. pass (slow, run below).
- N1: test_stairs_start_at_seed_file_and_end_at_trigger checks stairs[0] == the S0 file and stairs[-1] == the triggers.json entry. pass.
- N2: test_tlv2_oob_boundary. Mutant `>= 4` -> `> 4` in a scratch copy: KILLED (index 3 and index 4 give identical edges {1,4,6,10,12,16}; test_tlv_parser.py:105 fails; the other 6 tests pass). pass.
- N3: S1/S2/S3 are written as readable one-step substitutions. pass.

Gates (fresh scratch copy):
- `ruff check .` clean; `mypy src` clean (8 files).
- test_tlv_parser, test_mini_format, test_target_static_check, test_dedup, test_fuzzer and test_retune_odds (default selection): 90 passed, 9 deselected.
- `-m slow` test_retune_odds, stairs_start + predicate_matches (S3 cross-check, both cfgs): 4 passed (125 s).
- Not re-run: the full `-m slow` depth sweeps and the 200k odds test. S0, SHA256SUMS and the staircase bytes are byte-identical to my bounce-1 measurement (slow suite 8 passed then). The developer reports 10 passed (680 s) after the fixes.

Path grep (home, scratch and temp path patterns) over every touched file, and the added lines in the AFL-010/016 Logs: no hits. docs/papers holds only .gitkeep. toy_parser is untouched.

## Log
- 2026-11-15 — created (req-engineer) from the lead decisions after the first pilot (lead decision, 2026-11-15)
- 2026-11-15 — phase 1, design and calibration in scratch (developer). Each step was made reachable by moving S0 next to unchanged comparisons, not by changing the comparisons: S0 now carries a dormant record, so every step is one substituted byte. Function, bug class, crash site, shallow bugs and ground_truth.json are unchanged.
- 2026-11-15 — phase 2, applied (developer). Files: targets/tlv_parser.c, targets/mini_format.c, the two S0 files, SHA256SUMS (two lines), triggers.json (mfp-1 only), tests/test_tlv_parser.py, tests/test_mini_format.py, new tests/test_retune_odds.py; retune lines appended to AFL-010 and AFL-016.
  - tlv-2 staircase (old: S0=010441424344, +7E00, +7E0158, +7E025810; new): S0 = 010441424344fe025900 (10 bytes, dormant extension record); S1 = ...7e025900 (marker FE to 7E, 3 new edges); S2 = ...7e025800 (selector Y to X, 1 new edge); S3 = ...7e025810 (index 0x10 >= 4, new edge ext-index-oob, then heap-buffer-overflow READ at parse_ext, signal 6). S3 equals the unchanged triggers.json tlv-2 value. Code change: one line in parse_ext, `if (p[1] >= 4) puts("ext-index-oob");`, a distinct edge on the crashing side (guards against the AFL-010 F2 block-pruning fragility); no comparison changed.
  - mfp-1 staircase (old: S0 = 4d46010041027879 42016b76, ver 02, +5403, +4702, idx 02 to 03; new): S0 = 4d460100 41027879 abff4700 42016b76 (16 bytes; under ver 1 the unknown type AB stops parsing, so T/G bytes are dormant); S1 = ver 02 (2 new edges); S2 = byte 8 AB to 54 (13 new edges, T accepted, size FF, G idx 0 in range); S3 = byte 11 00 to FF (idx == size, one-past edge, then heap-buffer-overflow READ at rec_get, signal 6). Comments only changed in mini_format.c; no comparison changed.
  - S0 SHA256, old to new: tlv_parser 0a00d89f003ab8c73423ac18e1b2594b063d646b5ae474e7cbd0f462e55d63be to 6568ab7dde40662855858d1a6f5715ac036a91578349d61f2e75a94df82f66c9; mini_format d2f6a1670fadffddee5942f7b39239f7fa7d6b2835fff856241c77bed36df756 to e02a07d88a0ca08f411b67cddd59bd3ee3a45e261e8720a02507e8e99bc27257. toy_parser line untouched.
  - triggers.json: tlv-2 unchanged (0104414243447e025810). mfp-1 old 4d4602004102787942016b7654034703, new 4d4602004102787954ff47ff42016b76. tlv-1 and mfp-2 entries unchanged (still crash at main and rec_data; they are no longer S0 one-byte substitutions because S0 changed, so tests compare them to literals).
  - Odds on the AFL-034 build, 200,000 mutants per step, seed 20261115 (tests/test_retune_odds.py; identical to the pre-AFL-034 scratch run because the predicate is edge-based): tlv-2 hits 273, 124, 2146 -> p = 1.365e-3, 6.20e-4, 1.073e-2, sum 1/p = 2439. mfp-1 hits 159, 1483, 342 -> p = 7.95e-4, 7.415e-3, 1.71e-3, sum 1/p = 1978. Both in [1,500, 3,000].
  - Predicate vs Executor edges, validated on a sample per step (scratch run: 547-2,654 mutants per step, 0 disagreements; the slow test re-checks about 150 positives + 150 random per step).
  - Single-byte sweeps on the final S0 (Executor, AFL-034 build): tlv_parser 10 x 256: crashes by site {main: 64}, none at parse_ext, 0 hangs. mini_format 16 x 256: crashes by site {rec_data: 4}, none at rec_get, 0 hangs.
  - Honesty caveat: the mfp step-2 predicate is "any new edge vs S1" (the AC's definition), so it counts alternate routes (B dispatch, normal loop exit) as well as a real T record; its p (7.4e-3) is generous. A stricter "T record accepted" key gives p = 2.57e-3 and a sum of 2232 (still in range), but the mirror then disagreed with Executor edges on 329 of 1,241 sampled mutants (the key edges depend on the table size and on what follows), so I did not use it. If the tester wants the strict figure, the predicate needs rework.
  - The odds measure edges, but AFL-034 retains on (edge, bucket); the staircase asserts keep the AC's "new edge" definition.
- 2026-11-15 — gates (developer): `ruff check .` clean; `mypy src` clean (8 files); default `pytest -p no:cacheprovider --no-cov` 571 passed, 10 deselected; `pytest -m slow -p no:cacheprovider --no-cov` 10 passed, 571 deselected (632 s; the three depth sweeps and tests/test_retune_odds.py). AFL-030 banned_forms on both retuned sources: none. `git diff --stat targets/ground_truth.json` empty. Moved backlog -> in-progress -> review (plain mv). ACs are left for the reviewer to tick; evidence is the lines above (developer)

## Review (reviewer, 2026-11-15) — CHANGES REQUESTED

Verdict: bounce to in-progress (bounce 1). The retune design is sound and the
calibration holds, but three AFL-010/AFL-016 ACs that this ticket must keep green
("Every AC of AFL-010 and AFL-016 still passes") are broken by the S0 change. All
evidence below was produced on a scratch copy (fresh `make -C targets clean all`).

Verified (pass):
- Identity: `git diff targets/ground_truth.json` empty. Via Executor: tlv-2 trigger
  heap-buffer-overflow READ at parse_ext, SIGABRT; mfp-1 trigger heap-buffer-overflow
  READ at rec_get, SIGABRT. No comparison changed; the only code change is the tlv
  `ext-index-oob` line. AFL-030 static test passes on both sources.
- Depth: staircases re-measured with Executor. tlv new edges per step [10,12,14],
  [16], [17]; mfp [8,11], 13 edges, [58]. S0..S2 clean, S3 crashes at the bug's
  function. k = 3 meets AFL-010/AFL-016 wording. `pytest -m slow` (odds, predicate
  check, both sweeps over 10x256 and 16x256): 8 passed, 535 s; hit counts reproduce
  the Log exactly (273/124/2146 and 159/1483/342).
- Shallow bugs still shallow from the new S0: T1 = 015041424344fe025900 crashes
  stack-buffer-overflow WRITE at main; T2 = 4d46010041057879abff470042016b76 crashes
  stack-buffer-overflow WRITE at rec_data.
- mutate() use matches fuzzer.py (same signature, injected rng, pool of seed bytes).
  Mirror fidelity: 780 extra Executor runs targeted at likely false negatives
  (mirror-negative mutants whose labels differ from the parent's, plus mirror-negative
  mutants that take tlv's X branch) gave 0 disagreements.
- Mutants (scratch): M1 drop the tlv `ext-index-oob` line, killed by
  test_tlv2_deep_staircase (step 3 adds no edge, the F2 case). M2 tlv S0 := S2 with a
  consistent SHA256SUMS, killed by the staircase test and by the slow sweep (parse_ext
  reached). M3 mfp S0 := S2 with a consistent SHA256SUMS, killed by the staircase test
  and by the slow sweep (rec_get reached).
- ruff, mypy clean; touched fast tests, static check, fixture and dedup tests pass.
- No absolute or scratch paths in any file this ticket touched.

Must fix:
1. Trigger-table AC conflict (AFL-010 AC "Symbolizer-check trigger entries": "the
   input is one this ticket documents: tlv-1's single-substitution trigger"; AFL-016
   same AC: "mfp-2's T2"). triggers.json tlv-1 = 015041424344 and mfp-2 =
   4d4601004105787942016b76 are single substitutions of the OLD S0, not the shipped
   one. This conflicts with AFL-035 AC 2 ("entries are unchanged"). The tests were
   changed to compare against literals, which drops the S0-to-trigger link those ACs
   tested. Needs a lead ruling. Recommended: update both entries to the new T1/T2
   above (both verified to crash at the right site) and restore the asserts
   `== T1` / `== T2`; amend AC 2 to "shallow bugs unchanged (function, class, site);
   entries are the new S0's single-substitution triggers". The alternative is a lead
   waiver of the two AFL-010/016 AC sentences.
2. tlv_parser.c header no longer matches AFL-010 ACs "tlv-1 is shallow" and "Guarding
   branch (b)". "T1 = S0 with byte 1 substituted (0x04 -> 0x50), i.e. 01 50 41 42 43 44"
   is self-contradictory (the literal is 6 bytes, S0 is 10). "benign-below-bound
   01 04 41 42 43 44 (= S0)" is false. "rejected by the guard at line 65" is now line
   71. AFL-010 AC 3's literal "T1 = 01 50 41 42 43 44" is part of the same conflict
   (include it in the lead ruling under item 1). Fix the header to document the inputs
   the tests actually measure.
3. AFL-007 fixture not kept current (AFL-010 AC "AFL-007 fixture kept current"). The
   tlv-1 ASan report changed: frames main tlv_parser.c:69 -> :75 and :56 -> :62, and
   the source sha256 recorded in the fixture header (6c215890...) is now 4c9c4ce1....
   test_fixture_not_stale passes only because it compares function names. Re-capture
   tests/fixtures/tlv_parser_asan_memcpy.txt from the new build, update its header,
   and add the fixture to this ticket's module list.

Should fix (record in the Log; for the lead and the AFL-024 threats):
- S1. Calibration spread and alternate routes. Independent mirror runs (seeds 99 and
  4242, plus 31337/555 for the dominant steps) pool to tlv sum ~2,650 (step 2 hits
  124/100/108/120 per 200k; the Log's seed is the low end) and mfp ~2,080 (generous) or
  2,320-2,530 (strict: T accepted, or T accepted + G read). All are inside
  [1,500, 3,000], so the generous mfp predicate is not material. But the staircase sum
  overstates real cost. From tlv S1, about 7.2e-4 of mutants crash at parse_ext
  directly (arith on the 16-bit window 59 00 -> 58 xx), which is more than p2 and
  outside the step-2 predicate (Executor agrees: they take edge 17, not 16). The
  effective expected cost is about 750 + 1/(p2 + p_direct) + ... ~ 1,570, at the
  bottom of the band. mfp has a parallel route: T before ver 2 (S0 with AB -> 54 is
  retained under ver 1, p ~ 2.8e-3). Disclose both.
- S2. Disclose the S0 change's side effects on the shallow bugs and the seeds.
  mfp-2 single-byte triggers go from 2 to 4 (len 05..08 now fit). The mfp S0 no longer
  parses its B record (S0 13 edges vs 17 before). tlv byte 1 is 1 of 10 positions, not
  1 of 6. Both S0s now carry a dormant, hand-placed record next to the bug ("seed
  engineering"); depth is relative to these seeds. These are arm-neutral but change
  the targets.
- S3. Strengthen test_predicate_matches_executor_edges against false negatives: 150
  random draws contain about 0.1-1.5 positives. Add mirror-negative mutants whose
  labels differ from the parent's.

Nits:
- N1. tests/test_retune_odds.py hard-codes the stairs. Assert that stairs[-1] equals
  the triggers.json entry (and ideally the target tests' STAIRCASE).
- N2. No test covers the tlv oob boundary (index 4 takes the `ext-index-oob` edge).
  A `> 4` mutant would survive.
- N3. test_tlv_parser.py:25 builds S2 from STAIRCASE[1] and S0 together. It is
  correct but hard to read.

Pre-registration notes for the lead (not blocking):
- AFL-011's probe-phase exec/s, D_max, k = 3, the timeout_s floor and c = 3 were all
  measured on 282f2ea/dc54baf, which has the old tlv/mfp sources and S0s and the
  old mfp-1 trigger. Per-exec cost is dominated by process start and ASan, so 4 more
  S0 bytes should not move exec/s. The crash mix does shift: fewer tlv-1 hits per
  mutation, more mfp-2. c = 3 was set by toy_parser, which is untouched (77.5 %).
  The floor is 3 x 0.345 = 1.04 s against timeout_s 5.0, so the margin is large.
  Nothing here looks invalidated. The confirmation pilot, plus item (h)'s
  crash-duration run and the timing-probe numbers on the freeze commit, re-measure
  all of it on the retuned targets. That seems enough, provided the freeze Log
  records that the probe numbers predate the retune.
- 2026-11-15 — review (reviewer): CHANGES REQUESTED, bounce 1. Must-fix 1-3 (trigger-table AC conflict with AFL-010/016, needs a lead ruling; tlv_parser.c tlv-1 header stale; AFL-007 fixture not re-captured); calibration independently confirmed in range (tlv ~2,650, mfp ~2,080-2,530 pooled); 3 mutants killed; slow suite 8 passed. Moved review -> in-progress (reviewer)
- 2026-11-15 — bounce 1 fixes (developer). (1) Shallow triggers follow the new S0: triggers.json tlv-1 = 015041424344fe025900 (Executor: stack-buffer-overflow WRITE at main, signal 6) and mfp-2 = 4d46010041057879abff470042016b76 (stack-buffer-overflow WRITE at rec_data, signal 6); `== T1` / `== T2` asserts restored in both test_trigger_table tests; AC 2 reworded. AFL-010 AC 3's literal "T1 = 01 50 41 42 43 44" refers to the pre-retune S0 and is superseded by this retune; AFL-010 and AFL-016 AC text is not edited. (2) tlv_parser.c header: T1 literal and the three guard-side inputs are now the 10-byte S0 forms, "(= S0)" is true for the benign example, line numbers dropped; mini_format.c header gains the T2 literal and notes four single-byte triggers (no line numbers there). (3) tests/fixtures/tlv_parser_asan_memcpy.txt re-captured via Executor on the new tlv-1 trigger; header sha256 a3c01b3c662f1f4ba409315ecbc9c3041d21edce29f747e194179b2f9232a99e equals sha256 of the current targets/tlv_parser.c (frames now main tlv_parser.c:75, frame at :62); no mini_format fixture exists. tlv_parser.c must not be edited again without re-capturing it.
- 2026-11-15 — disclosures (developer, from the reviewer's numbers). S1: tlv has a direct route S1 -> crash at about 7.2e-4 (arith on the 16-bit window 59 00 -> 58 xx; it takes the oob edge, outside the step-2 predicate), so the effective expected cost is about 1,570 against a staircase sum of about 2,650 pooled over seeds (the Log's 2,439 is one seed); mfp has a parallel route, the T record before ver 2 (S0 with AB -> 54 is retained under ver 1), at p about 2.8e-3. S2: mfp-2 now has 4 single-byte triggers (len 05..08, was 2); the mfp S0 no longer parses its B record (13 edges against 17 before); tlv-1's byte is now 1 of 10 positions (was 1 of 6); both S0s carry a hand-placed dormant record next to the bug, so depth is relative to these seeds (arm-neutral, but the targets changed). Tests: S3 near-miss sampling (mirror-negative mutants whose labels differ from the parent's) added to the Executor cross-check; N1 the last staircase input must equal the triggers.json entry; N2 test_tlv2_oob_boundary (index 3 clean, index 4 takes the oob edge and crashes); N3 test_tlv_parser.py staircase split into S1/S2/S3.
- 2026-11-15 — bounce 1 gates (developer): `make -C targets clean all`; `ruff check .` clean; `mypy src` clean (8 files); default `pytest -p no:cacheprovider --no-cov` 572 passed, 10 deselected; `pytest -m slow -p no:cacheprovider --no-cov` 10 passed, 572 deselected (680 s). Odds numbers unchanged (S0 and staircases untouched). Moved in-progress -> review (developer)
- 2026-11-15 — re-review (reviewer): APPROVED. Must-fix 1-3 and S1-S3, N1-N3 verified; N2 mutant (`> 4`) killed; fixture matches a fresh build (sha a3c01b3c...); gates green in scratch. Follow-up recommended (AFL-007 gap, not this ticket): no test checks the fixture header sha, so a future tlv_parser.c edit breaks no test. Moved review -> testing (reviewer)
- 2026-11-15 — verification (tester): PASS. Gates: ruff clean, mypy clean (8 files), default pytest 572 passed / 10 deselected, `pytest -m slow` 10 passed / 572 deselected (687 s); no real campaign or pilot was running. Independent odds (real mutate(), seed 777+step, 150,000 mutants per step, test_retune_odds predicate): tlv-2 hits 190/89/1619, p = 1.27e-3, 5.9e-4, 1.08e-2, sum 1/p = 2568; mfp-1 hits 157/1091/211, p = 1.05e-3, 7.27e-3, 1.41e-3, sum 1/p = 1804. All within about 2.5 standard errors of the Log's p (worst: mfp step 1, 1.05e-3 vs 7.95e-4); both sums in [1500, 3000]. Executor on a fresh scratch build: all six triggers crash at their ground_truth function with the expected class; staircases S0..S2 clean and S3 crash, new edges tlv 3/1/1, mfp 2/13/1; S0 sha256 matches SHA256SUMS; fixture header sha matches targets/tlv_parser.c. ground_truth.json, toy_parser (source, S0, SHA256SUMS line), mutator.py and schedule.py have no diff. AFL-030 static check passes. Note: the reviewer's path-grep sentence in this ticket names the grep patterns, so a literal grep for them matches that one line; no actual path appears. Left in testing for the crew-lead's gated close (tester)
- 2026-11-15 (crew-lead): DoD verified; closed via gated move.
