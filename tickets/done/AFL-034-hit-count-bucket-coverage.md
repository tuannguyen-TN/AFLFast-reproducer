---
id: AFL-034
title: Switch coverage granularity to AFL hit-count buckets (edge, bucket) pairs
requirement: FR-1 / FR-3 / FR-5 (and the AFL-011 AC "Pilot + coverage-granularity fallback (pre-registered, ADR-0001)")
paper_ref: AFLFast (f(i) counts path ids) and AFL whitepaper (hit-count buckets)
module: targets/cov_rt.c, src/fuzzer/coverage.py (+ any minimal change elsewhere strictly needed to keep edges/final_edges as distinct edge ids, recorded in ADR-0001), docs/adr/0001-coverage-mechanism.md, tests
depends_on: [AFL-002, AFL-011]
status: done                       # backlog|in-progress|review|testing|done
owner: developer
---

## Goal
The pre-registered granularity rule fired on the first pilot (toy_parser and
tlv_parser), so coverage moves from plain edge sets to AFL hit-count buckets:
retention, `path_id` and f(i) use (edge, bucket) pairs, while the primary
endpoint keeps its pre-registered meaning (distinct edge ids hit by clean
executions). Data-affecting: **Opus review**.

First-pilot evidence (run on d9a22db, results/pilot/first_pilot, seeds 2000..2002,
c = 3, pooled over both arms, n = 6 per target, final metrics.csv row, evaluated
2026-11-16 UTC): toy_parser median distinct_path_ids 4.5 / median corpus_size 3.5
(fires, < 20); tlv_parser 14.0 / 8.0 (fires, < 20); mini_format 65.5 / 20.0 (does
not fire). results/pilot/granularity_decision.json agrees: trigger_fired true,
granularity "hit_count_buckets".

Lead decision (2026-11-15), the substance of this ticket: switch to AFL hit-count
buckets (the rule fired on toy_parser and tlv_parser). `cov_rt.c` keeps a
saturating 8-bit counter per guard; `coverage.py` buckets the counts AFL's way
(1, 2, 3, 4-7, 8-15, 16-31, 32-127, 128+). Retention, `path_id` and f(i) use
(edge, bucket) pairs. The primary endpoint keeps its pre-registered meaning:
`edges` and `final_edges` stay the number of distinct edge ids hit by clean
executions (ADR-0005 §6), not a count of (edge, bucket) pairs. If that needs a
small change outside the two seam files, make it, and record the exception
honestly in ADR-0001 together with the granularity decision: it is what keeps the
endpoint's definition intact.

Note: the AFL-011 AC says "no other module changes" for the seam. The lead
decision (2026-11-15) explicitly allows the small endpoint-preserving exception.

## Acceptance criteria
- [x] (a) Counter: `targets/cov_rt.c` keeps one saturating unsigned 8-bit counter per guard; a counter at 255 stays 255 (test or static check on the C source plus a behavioural run of a target hitting a guard > 255 times).
- [x] (b) Bucketing: `coverage.py` maps a count to exactly the 8 AFL buckets 1, 2, 3, 4-7, 8-15, 16-31, 32-127, 128+; count 0 is "not hit" and yields no (edge, bucket) pair.
- [x] (c) Granularity: corpus retention, `path_id` and f(i) are computed over (edge, bucket) pairs; a candidate that changes only the bucket of an already-seen edge is retained.
- [x] (d) Endpoint: `edges` and `final_edges` (metrics.csv, ADR-0005 §6) remain the number of distinct edge ids hit by clean executions and are unchanged by bucket counts (same input, same edge ids hit, different hit counts -> same `edges`).
- [x] (e) Any change outside `cov_rt.c` and `coverage.py` is minimal, named in this ticket's Log, and recorded as an exception in ADR-0001.
- [x] (f) ADR-0001 gains a dated amendment recording the granularity decision, the first-pilot medians above, and the exception from (e) (or its absence).
- [x] (g) Tests: bucket boundaries (each of the values 1, 2, 3, 4, 7, 8, 15, 16, 31, 32, 127, 128, 255 lands in the stated bucket), saturation (255 stays 255), retention on a bucket change alone, and `final_edges` unchanged by the bucket count.
- [x] (h) Invariants: mutation stays blind (`src/fuzzer/mutator.py` unchanged); both arms get the same change, arms differ only in `schedule.py`; the replay guarantee of ADR-0005 still holds (the existing replay tests pass unmodified).
- [x] (i) `ruff check .`, `mypy src` and `pytest` pass.

## Technical notes (architect)
- Files: `targets/cov_rt.c` (guard counter), `src/fuzzer/coverage.py` (read + bucket), `src/fuzzer/corpus.py` and `src/fuzzer/fuzzer.py` consume coverage (touch only if needed for (d), then record per (e)); `docs/adr/0001-coverage-mechanism.md`; ADR-0005 §6 defines `edges`/`final_edges`.
- `harness/` is NOT to be edited by this ticket: AFL-031 is editing `harness/run_campaign.py` in parallel. If a harness change is needed, report it instead.
- Targets are rebuilt with `make -C targets` (Homebrew LLVM, ADR-0001); the statically checked source rules (AFL-030) still apply to target sources.
- Data-affecting: Opus review. This ticket lands before the AFL-011 freeze; AFL-035 depends on it.

## Test approach (tester)
Unit tests per (g); replay tests unchanged; a short real-binary run showing a bucket-only change is retained while `edges` does not move; mutation of the bucket table and of the saturation guard must fail the tests.

## Review notes (reviewer, 2026-11-15): BOUNCE, round 1

Source is correct; the bounce is for test gaps on the endpoint and f(i), plus one ADR sentence.
Mutants were run on a scratch copy (repo source untouched).

Must fix:
1. AC (d)/(g): the endpoint is tested only on `Corpus.seen`, not on the metrics.csv `edges`
   column that `final_edges` is read from. Mutant `state = (len(corpus.seen_hits), ...)` in
   `_Recorder.tick` (fuzzer.py) passes the whole suite. Add a stub test in tests/test_fuzzer.py:
   S0 clean `{(1, 1)}`, exec 2 clean `{(1, 8)}`, the rest `{(1, 1)}`; assert every metrics row
   has `edges == "1"`, and the final row has `corpus_size == "2"` and `distinct_path_ids == "2"`.
   This also kills mutant 2 below. Checked on scratch: it kills both.
2. AC (c): f(i) over pairs is untested. Mutant `pid = path_id(frozenset((e, 1) for e in
   result.edges))` in `Corpus.observe` passes the whole suite. So does the same edge-only
   mutant on the clean-branch `rec.path_ids.add(...)` in fuzzer.py, which is killed by item 1.
   Add a Corpus test: observe `{(1, 1)}`, then `{(1, 8)}`, then `{(1, 1)}`; both seeds are
   retained with `path_freq` 2 and 1. Checked on scratch: it kills the mutant.
3. AC (f): the ADR-0001 amendment implies, but does not say, that `distinct_path_ids` now
   counts distinct (edge, bucket) sets. That column is read by the AFL-011 pilot rule and is
   recorded by the confirmation pilot. Say it explicitly in the amendment, and name the
   wording it supersedes: ADR-0005 s6 ("`coverage.path_id(r.edges)`", "counts distinct edge
   sets", and the "Remaining difference from AFL ... presence only" bullet), and ADR-0004 s2
   "(over the presence edge set, ADR-0001)". PRD deviation (iv) ("presence-only retention
   keeps a subset of what AFL's hit-count bucketing keeps") is now stale too. Editing the PRD
   is out of this ticket's scope, so the amendment names it and the lead is told.

Should fix (cheap, do with the bounce):
- The AFL-002 branch-distinctness tests (`test_each_branch_side_distinct_toy`,
  `test_branch_distinct_tlv`, tests/test_coverage_spike.py) now compare pair sets. ADR-0001
  says they assert distinct *edge* sets, and pair-distinct is weaker than edge-distinct.
  Checked on scratch with the new cov_rt.c: today the two are the same (every ladder input
  hits each guard once), and an -O1 build of toy_parser and spike still fails the pair-level
  check. Project to edge ids, `frozenset(e for e, _ in s)`, so the tests keep the property
  ADR-0001 states.
- `ShmBitmap.edges()` no longer has a caller. Delete it.
- `test_counter_saturates_at_255_real_binary` takes the `toy` fixture without using it. Its
  second assert, `(int(bm._map.max()), 128) in {(255, b) ...}`, is convoluted and on its own
  does not kill a wrapping counter: 5 guards are >= 128 even when it wraps. Only
  `max() == 255` kills that mutant. Simplify the second assert to
  `(int(bm._map.argmax()), 128) in bm.hits()`.

Nits:
- ADR-0001: AFL 2.x (the base of AFLFast) wraps its 8-bit counters, and AFL++ "NeverZero"
  avoids the wrap to 0. Saturation is a small, disclosed difference from AFLFast. Say so in
  one clause.
- Crash save rule (c) keys on `path_id`, so pair-based ids will save more crash inputs (at
  most 8 buckets per edge). Check the disk use in the confirmation pilot.

Verified OK:
- cov_rt.c `v + (v != 255)` saturates. A real build that wraps (`v + 1`) gives max 244 on the
  500-record input and fails the test; the real build gives 255, deterministic over 3 runs.
- The executor resets the bitmap before every run, and a timeout returns empty hits.
- Targets are single-threaded, with no fork and no forkserver or persistent mode. No target
  .c changed.
- The LUT is exactly AFL's `count_class_lookup8`. Mutants at 4->5, 15/16, 32->33 and
  128->129 are all killed by `test_bucket_boundaries`. Count 0 gives no pair.
- `path_id` is blake2b over the sorted (edge u32 LE + bucket byte) pairs. It is deterministic
  and independent of order. A mutant that drops the bucket and a mutant that skips the sort
  are both killed.
- Mutant "retention on edge ids" is killed.
- `mutator.py`, `schedule.py` and `harness/` are untouched by this ticket. Both arms get the
  same change.
- The replay test is unmodified. The test_cli.py stub line and the new `path_id` constant
  are forced by the type change and do not weaken anything: a mutant that drops the bucket
  makes `path_id` return the old constant, so the new one pins the bucket byte.
- The ADR medians match results/pilot/granularity_decision.json.
- The endpoint is the same function of the executions as before. Invariant: `seen` equals
  the edge-id projection of `seen_hits`. So any clean execution with a new edge id carries a
  new pair and is retained, and `seen` remains the union of the edge ids of all clean
  executions. Crash and hang executions never reach `observe`.

## Review notes (reviewer, 2026-11-15): APPROVE, round 2

All three must-fix items and all three should-fix items from round 1 are done. Mutants were
re-run on a fresh scratch copy of src/ and tests/ with bytecode caching off; the repo source
was not touched.
- Killed: M1-M3b (LUT boundaries), M4 (retention on edge ids), M5 (metrics `edges` taken
  from `seen_hits`; killed by `test_bucket_change_moves_corpus_and_paths_not_edges`), M6
  (path_id drops the bucket), M7 (Corpus f(i) over edge ids; killed by
  `test_path_freq_counts_over_edge_bucket_pairs`), M8 (clean `distinct_path_ids` over edge
  ids; killed by the new fuzzer test), M9 (path_id unsorted), M10 (`seen_hits` never updated).
- Wrapping counter `v + 1`, built in scratch: `test_counter_saturates_at_255_real_binary`
  fails (244 != 255). A clean scratch rebuild with the real cov_rt.c passes.
- ADR-0001 addendum: accurate and honest, with no home or scratch paths. It states the change
  to `distinct_path_ids`, names the superseded ADR-0005 s6 and ADR-0004 s2 wording, flags PRD
  deviation (iv) to the lead, and discloses that AFL 2.x wraps its counters while we saturate.
- Makefile: `$(BIN)/%: %.c cov_rt.c` does depend on cov_rt.c. The developer's "no dependency"
  claim is wrong. Their stale scratch binary was an mtime artefact: a copy or touch in the
  same second as the build leaves make with nothing newer. Repo binaries (20:54:33) are newer
  than cov_rt.c (20:54:23).

Nits, not blocking:
- When the real-binary saturation assert fails, the finally `bm.close()` also raises
  BufferError, because pytest's assertion introspection holds a reference to `bm._map`. The
  test still fails correctly. Only the report is noisier.
- Fix the developer's Makefile claim in the Log so it does not mislead later readers.
- Lead follow-up: the PRD deviation (iv) wording, and the ADR-0005 s6 / ADR-0004 s2 text,
  which this amendment supersedes but does not edit.

## Log
- 2026-11-15 — created (req-engineer) from the lead decisions after the first pilot (lead decision, 2026-11-15)
- 2026-11-15 — (developer) implemented. Seam: `targets/cov_rt.c` (saturating counter `v + (v != 255)`), `src/fuzzer/coverage.py` (BUCKET_LUT, `ShmBitmap.hits()`, `path_id` over (edge, bucket), `run_with_coverage` returns pairs). Outside the seam (AC e, recorded in ADR-0001 amendment 2026-11-15): `executor.py` (`ExecResult.edges` field -> `hits`, `edges` now a derived property of distinct ids), `corpus.py` (`seen_hits` retention key; `seen` stays distinct edge ids), `fuzzer.py` (4x `path_id(r.hits)`). `schedule.py`, `mutator.py`, `harness/` untouched. Tests: new in tests/test_coverage.py (bucket boundaries, saturation source + real mini_format run with 500 loop iterations, bucket-only retention, edges unchanged); existing test stubs changed only to build `ExecResult` with `(edge, 1)` pairs (tests/test_fuzzer.py, test_corpus.py, test_schedule.py, test_cli.py, test_mini_format.py), plus test_path_id fixed value (hash input now includes the bucket byte). ADR-0005 replay tests unmodified.
- 2026-11-15 — (reviewer) BOUNCE (round 1) -> in-progress. Must fix: (1) metrics.csv `edges` not guarded against bucket counts (mutant len(corpus.seen_hits) in tick survives); (2) f(i) over pairs untested (edge-only path_id mutant in Corpus.observe survives); (3) ADR-0001 amendment must state distinct_path_ids now counts (edge, bucket) sets and name the superseded ADR-0005 s6 / ADR-0004 s2 / PRD deviation (iv) wording. Should-fix: edge-projection in AFL-002 distinctness tests, delete dead ShmBitmap.edges(), simplify saturation test. Source itself verified correct. Gates: ruff clean, mypy src clean, targeted pytest 188 passed, pytest -m slow 4 passed (494 s). See "Review notes". (reviewer)
- 2026-11-15 — (developer) bounce round 1 fixed. Must-fix: tests/test_fuzzer.py `test_bucket_change_moves_corpus_and_paths_not_edges` (every metrics row edges == "1", final corpus_size 2, distinct_path_ids 2); tests/test_corpus.py `test_path_freq_counts_over_edge_bucket_pairs` (path_freq 2 and 1); ADR-0001 addendum (distinct_path_ids now counts (edge, bucket) sets; supersedes ADR-0005 s6 and ADR-0004 s2 wording; PRD deviation (iv) stale, PRD follow-up for the lead; AFL 2.x wraps counters, we saturate; ADR-0004/0005/PRD not edited). Should-fix: AFL-002 distinctness tests (test_coverage.py, test_coverage_spike.py) compare edge ids; dead `ShmBitmap.edges()` deleted (no callers in src/harness/tests); saturation test drops `toy`, asserts `(argmax, 128) in bm.hits()`. Mutants on scratch scratch (no bytecode): M5 killed (new fuzzer test), M8 killed (new fuzzer test), M7 killed (new corpus test), wrap-counter killed (real-binary test, 244 != 255, plus source test; note the Makefile bin rule does not depend on cov_rt.c, so the scratch binary had to be deleted to rebuild). Gates: ruff clean, mypy clean, pytest 571 passed, 4 deselected. (developer)
- 2026-11-15 — (reviewer) APPROVE (round 2) -> testing. Round-1 must-fixes verified: M5, M7 and M8 now killed; M1-M10 and wrap-counter killed (scratch, no bytecode); ADR-0001 addendum accurate, no local paths. Gates: ruff clean, mypy src clean, targeted pytest 190 passed / 4 deselected. Makefile does depend on cov_rt.c (developer's claim wrong; same-second mtime artefact). Nits in "Review notes ... round 2". (reviewer)
- 2026-11-15 — (tester) PASS, left in testing for the crew-lead's gated close. Gates: ruff clean, mypy src clean (8 files), default pytest 571 passed / 4 deselected (110 s), pytest -m slow 4 passed (495 s); no campaign running. Scratch rebuild (`make clean all` on a copy of targets/): mini_format 500-iteration loop gives raw counter 255 (saturated, not 244) and bucket 128; `ExecResult.edges` equals the edge ids of `hits` on all runs. toy_parser has no loop (every guard fires once, max bucket 1 on every input tried), so the "toy loop gives bucket > 1" check is not applicable; bucket > 1 is shown on mini_format (14-byte input -> bucket 8). Mutants on scratch (no bytecode), all killed: LUT 8->9 (`test_bucket_boundaries[8-16]`), M5 metrics edges from seen_hits (`test_bucket_change_moves_corpus_and_paths_not_edges`), M7 Corpus path_id over edge ids (`test_path_freq_counts_over_edge_bucket_pairs`). Validity: mutator.py and schedule.py have no diff; harness/ diff is AFL-031's only; endpoint is len(corpus.seen), distinct edge ids. Path hits: none in AFL-034 source/tests/ADR diff; this ticket file's own Log line (developer, bounce round 1) names a scratch path under scratch (cosmetic, ticket only). (tester)
- 2026-11-15 closed (crew-lead): DoD verified; gated move to done.
- 2026-11-16 — correction (req-engineer, AFL-036): the developer's bounce-round-1 Log line says "the Makefile bin rule does not depend on cov_rt.c"; that is wrong. targets/Makefile has `$(BIN)/%: %.c cov_rt.c`, so every target binary depends on cov_rt.c (the reviewer confirmed this in round 2); the stale build was a same-second mtime artefact. Log append only; no other line of this ticket changed. (lead decision, 2026-11-16)
