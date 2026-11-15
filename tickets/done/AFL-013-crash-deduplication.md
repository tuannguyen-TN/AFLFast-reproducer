---
id: AFL-013
title: Crash de-duplication (crash-site bucketing)
requirement: FR-6
paper_ref: Klees § performance measures (crash de-duplication overcounts; ground truth)
module: harness/dedup.py
depends_on: [AFL-003, AFL-007]
status: done
owner: tester
---

## Goal
Bucket every crash event of a trial by crash site, so that "unique crashes" does
not overcount bugs (FR-6, PRD §8). The heuristic must be named, and its known
biases stated, as Klees requires.

Open questions (PRD silent or ambiguous; resolve before leaving backlog):
- ~~FR-6 says "PC / top-of-stack hash" but gives no stack depth N, and does not say
  whether to use the faulting PC alone or a hash of the top N frames.~~
  **Resolved (human, 2026-11-07):** the bucket key is the crash site returned by
  AFL-007's shared extraction function in `src/fuzzer/` (first in-target frame of
  the ASan report); no top-N hash, and the signal is not part of the key. See the
  "Bucket key" and "ADR-0003" ACs.
- ~~The PRD does not say where the "faulting context" comes from: the ASan report,
  a symbolized stack trace, or something else.~~ **Resolved (human, 2026-11-07):**
  the symbolized ASan report in `stderr`, parsed by that shared function.
- ~~FR-6 lists both `executor.py` and `dedup.py`. This ticket assumes saving crashes
  is in scope here, extending executor.py where needed, after AFL-003. Confirm.~~
  **Resolved (human, 2026-11-07):** saving is AFL-007's (save rule there); this
  ticket only reads `crash_events.csv` and the saved inputs. executor.py is
  unchanged.
- ~~PRD §8(c) measures time-to-first-crash **per planted bug**. That needs a map
  from bucket to planted bug (ground truth). The PRD does not say how to build
  that map. (Proposed default in Technical notes; still to confirm.)~~
  **Resolved (lead decision, 2026-11-14):** the bucket-to-bug mapping is exact
  function-name equality within the trial's target, with no per-bucket replay
  check. The CSV `crash_site` is already the extractor's output on that input's
  own report and is process-invariant (ADR-0005 §3); AFL-011's pre-flight
  symbolizer check covers a changed binary or a broken symbolizer.

## Acceptance criteria
- [x] **Source is the event stream (human decision, 2026-11-07).** `bucket_trial`
      reads `<trial>/crash_events.csv` (AFL-007) and buckets **every** crash event
      in it by its `crash_site` column. Saved crash inputs under `<trial>/crashes/`
      exist only for replay (checking a bucket's mapping to a planted bug); they
      are never counted and never used to form buckets. Test: a trial with N
      `crash_events.csv` rows at one site, of which only 1 has a saved input,
      yields one bucket with `count == N`.
- [x] **Bucket key is the crash site only (human decision, 2026-11-07).** The
      bucket key is the `crash_site` value; the signal is not part of it. Test: two
      events with the same `crash_site` and different `signal` land in one bucket.
- [x] Two crash events that hit the same crash site land in the same bucket.
- [x] Crash events at different crash sites land in different buckets.
- [x] The unique-crash count reported equals the number of buckets.
- [x] The heuristic is documented: named in the module docstring or README, with
      its known overcounting bias acknowledged (PRD §8, Klees).
- [x] **Known merge bias in the docstring (human decision, 2026-11-07).**
      `harness/dedup.py`'s module docstring states that two bugs in one function
      merge into one bucket (site = function), and that this is why every planted
      bug sits in its own function. Test: the docstring contains this statement
      (review/grep check).
- [x] **ADR-0003 records the FR-6 interpretation (human decision, 2026-11-07).**
      This ticket writes `docs/adr/0003-*.md`, which records that FR-6's
      "PC / top-of-stack" is interpreted as the first in-target stack frame (the
      AFL-007 shared extractor), that the key is the site only (no signal), and the
      sentinel handling below. Present before this ticket leaves review.
- [x] **ADR-0003 carries over the ADR-0005 §3 symbolizer note (added 2026-11-12,
      human decision).** When ADR-0003 is written, it either moves into itself the
      ADR-0005 §3 paragraph "A missing symbolizer gives `no_target_frame`" (a
      failed symbolization, or a target built without `-g`, is labelled
      `"no_target_frame"`, not `"unsymbolized"`, so that sentinel does not tell
      "symbolization failed" apart from "crashed outside the target"), or
      references ADR-0005 §3 explicitly for it. Test: review/grep check that
      `docs/adr/0003-*.md` contains that content or a reference to "ADR-0005 §3".
- [x] **Shared crash-site extractor (human decision, 2026-11-07; reworded for the
      event-stream source, human decision, 2026-11-07).** The bucket key is the
      `crash_site` column, which AFL-007 fills with the crash-site extraction
      function in `src/fuzzer/`. dedup.py uses that value verbatim and has no
      extraction or frame-parsing logic of its own. Reason: `crash_events.csv`
      and this ticket's buckets must agree on the crash site, otherwise per-bug
      time-to-first-crash (from the event stream) will not line up with
      unique-crash counts (from dedup). Test: for one captured ASan report
      (AFL-007's `tests/fixtures/` tlv_parser report), a `crash_events.csv` row
      whose `crash_site` is the `src/fuzzer/` function's output for that report
      yields a bucket whose key equals that output; a grep check finds no ASan
      frame-parsing code (e.g. `#\d+ 0x` patterns) in `harness/dedup.py`.
- [x] **Sentinels carried through, never merged (human decision, 2026-11-07).**
      Each of the three AFL-007 sentinels (`"no_stack"`, `"unsymbolized"`,
      `"no_target_frame"`) gets its own unknown-crash bucket (`bug_id=None`),
      never merged with a real crash-site bucket or with another sentinel's
      bucket. Tests: a trial with one crash at a real site and one addresses-only
      crash at the same planted bug yields two buckets, one with the real site and
      one `"unsymbolized"` bucket reported as unknown; a trial with one event of
      each sentinel yields three separate unknown buckets.
- [x] **Every real bucket has a replay input (human decision, 2026-11-07).**
      `Bucket.example` is `Path | None`: the `saved` path (AFL-007's
      `crash_events.csv` column, relative to the trial dir) of the earliest event
      in the bucket with a non-empty `saved`, else `None`. Test: on a trial
      directory written by AFL-007's loop (e.g. a short `max_execs` run on
      tlv_parser), `example` is not `None` and the file exists for every
      non-sentinel bucket.
- [x] **`crash_site` is process-invariant (added 2026-11-12, human decision).**
      Enforces ADR-0005 §3, paragraph "`crash_site` is replay-safe (binding; human
      decision, 2026-11-07, AFL-013; confirmed 2026-11-12)": "So `crash_site`
      contains no absolute addresses and no PIDs, and identical crashes in
      different processes give the same string. AFL-013 / ADR-0003 must keep the
      format free of process-varying content, or this guarantee breaks." ADR-0003
      states this constraint. Test (needs clang): toy-2's trigger `b"!aaa"`
      (`targets/toy_parser.c`; the same input as `toy-2`'s entry in AFL-011's
      trigger table) is run twice through `Executor` against
      `targets/bin/toy_parser`, each run a separate target process. Both
      `fuzzer.fuzzer.crash_site(stderr, "toy_parser.c")` strings are identical and
      equal `toy-2`'s `function` in `targets/ground_truth.json` (`"scan"`). Neither
      contains `0x` or `/`, and neither contains either run's PID (the number in
      the report's `==<pid>==` prefix). Each run's stderr does contain its
      `==<pid>==` prefix, so the test is checking a report that carries
      process-varying content.

## Technical notes (architect)
- **Placement (→ ADR-0003, written by this ticket):** dedup runs offline in
  `harness/`. fuzzer.py writes `crash_events.csv` and saves crash inputs (format
  and save rule in AFL-007); dedup.py reads `crash_events.csv` and only references
  saved inputs via the `saved` column. The harness may import the fuzzer, never the
  reverse. Split: the executor classifies and captures stderr (AFL-003), the
  fuzzer extracts the site and saves (AFL-007), dedup buckets (this ticket).
  executor.py needs no change here.
- **Interfaces (`harness/dedup.py`):**
  ```python
  @dataclass(frozen=True)
  class Bucket:
      key: str                    # crash_site (real site or sentinel)
      first_elapsed_s: float
      first_execs: int
      count: int
      example: Path | None        # from crash_events.csv `saved`; None only if no event saved
      bug_id: str | None          # from targets/ground_truth.json

  def bucket_trial(trial_dir: Path) -> list[Bucket]: ...   # reads crash_events.csv; sorted by first_elapsed_s
  ```
  There is no `parse_frames`/`bucket_key` here: the key is the site-only value
  produced by AFL-007's shared extractor in `src/fuzzer/` and stored in the
  `crash_site` column.
  aggregate.py (AFL-012) and plots.py (AFL-014) take unique crashes as `len(buckets)`
  and unique-crashes-over-time as a step function over `first_elapsed_s`.
- **Heuristic (decided, human, 2026-11-07):** key = the crash site from AFL-007's
  shared extractor (first stack frame whose source belongs to the target, skipping
  ASan runtime/interceptor and libc frames), or one of its sentinels `"no_stack"`
  / `"unsymbolized"` / `"no_target_frame"`. Signal is not part of the key. No
  top-N frame hash. dedup.py never re-derives the site.
- **Why `example` is never `None` for a real bucket:** AFL-007 saves a crash when
  its `path_id` **or** its `crash_site` is new, so the first event of every site
  has a non-empty `saved`.
- **Faulting context:** the ASan report in `stderr` (`symbolize=1`, AFL-003). No
  separate debugger or symbolizer step.
- **Mapping to planted bugs** (resolved, lead decision, 2026-11-14): a bucket maps to bug B
  when its crash site equals the `function` of B among the trial's target's bugs
  in `targets/ground_truth.json` (AFL-009/010); no per-bucket replay check.
  Buckets that match nothing, and all sentinel buckets, get `bug_id=None` and are
  reported as unknown crashes. Per-bug TTFC = the minimum `first_elapsed_s` over
  that bug's buckets.
- **Documentation (AC):** the module docstring names the heuristic ("first
  in-target stack frame", shared with AFL-007) and states Klees' finding that
  stack-based bucketing overcounts (one bug, many stacks) and can also undercount
  (two bugs in one function merge). For planted bugs, the ground-truth mapping is
  the honest count.

## Test approach (tester)
Synthetic `crash_events.csv` files: rows at one site (different signals, one
saved) → one bucket with the full count; rows at different sites → separate
buckets; one row per sentinel → three unknown buckets. A short real tlv_parser
run checks that every non-sentinel bucket has an existing `example`. Grep/review
for the docstring statements and for absence of frame parsing in dedup.py;
ADR-0003 present.

## Review (reviewer, 2026-11-14)
**Verdict: changes requested -> in-progress** (first bounce).

Gates: `ruff check harness tests/test_dedup.py` clean; `mypy src` clean;
`pytest tests/test_dedup.py` 11 passed, 0 skipped (the clang tests ran, including the
real tlv_parser loop). Whole-repo ruff/pytest failures are in other tickets' in-flight
files and are not held against AFL-013.

Per AC:
1. Source is the event stream: met. `harness/dedup.py:54-62` reads every row of
   `crash_events.csv`; `saved` is used only for `example`. Test `test_dedup.py:28-32`
   (7 rows, 1 saved -> one bucket, count 7).
2. Key is site only: met. `dedup.py:56`; test `test_dedup.py:35-37` (signals 6 and 11, one bucket).
3. Same site, same bucket: met (`test_dedup.py:28-37`).
4. Different sites, different buckets: met (`test_dedup.py:40-44`, also checks sort order).
5. Unique count = number of buckets: met. One bucket per distinct key; ADR-0003:65-66 fixes `len(buckets)`.
6. Heuristic documented with overcount bias: met (`dedup.py:3-16`).
7. Merge bias in docstring: met (`dedup.py:14-15`, matches PRD section 8 "distinct function"); test `test_dedup.py:79`.
8. ADR-0003 records the FR-6 interpretation: met (`docs/adr/0003-crash-site-dedup.md:22-36`); test `test_dedup.py:83-86`.
9. Symbolizer carry-over: ADR-0003 side met (`0003:47-57` holds the full paragraph and names
   ADR-0005 section 3). The ADR-0005 pointer is still pending: `0005:196-198` still says
   "ADR-0003 is not written yet" as of this review. Left `[~]`, not a bounce reason (lead decision, 2026-11-14).
10. Shared extractor, no frame parsing: met. `dedup.py:23` imports only `SENTINELS`; the key is
    the column verbatim (`:56`); no `re`, no frame patterns. Tests `test_dedup.py:67-72`, `:75-77`.
11. Sentinels never merged: met. `dedup.py:64` forces `bug_id=None` for sentinels even when a
    ground-truth function shares the name (`test_dedup.py:60-64`); `:52-57` covers a real site
    plus all three sentinels as four separate buckets.
12. Every real bucket has a replay input: met. `dedup.py:61-62` (first non-empty `saved` in file
    order, which is exec order); real-run test `test_dedup.py:90-100` asserts buckets exist, so it is not vacuous.
13. `crash_site` process-invariant: met. ADR-0003:41-46 states it; `test_dedup.py:104-113` runs
    `b"!aaa"` in two processes, checks equality, the `==<pid>==` prefix is present, and no `0x`, `/` or PID.

Required changes:
1. **Cross-target bug_id mis-mapping (Klees honesty, PRD section 8(c)).** `bucket_trial(..., target=None)`
   (`dedup.py:38-39, 49-50`) matches function names across all targets. `tlv-1`'s function is
   `main`, and every target has a `main`, so with the default a toy_parser (or future mfp) crash
   whose first in-target frame is `main` gets `bug_id="tlv-1"`. Reproduced: a one-row CSV with
   `crash_site=main` returns `tlv-1` with `target=None` and `None` with `target="toy_parser"`.
   The dict comprehension also silently keeps the last of any function name shared between
   targets. bug_id feeds per-bug TTFC, which is in AFL-012's primary family, and ADR-0003:65-66
   advertises `target=None` to AFL-012/AFL-014. Fix: make `target: str` required and look up only
   that target's bugs. Raise `ValueError` when `target` has no entry in `ground_truth.json`, so a
   typo cannot quietly turn every bug into an unknown crash (all TTFCs censored). Update the
   docstring (`dedup.py:42-46`), ADR-0003:37-40 and 65-66, and the test calls that omit `target`.
   Add a test: the same `main` row maps to `tlv-1` under `target="tlv_parser"`, to `None` under
   `"toy_parser"`, and an unknown target raises.
2. **Open question 4 (ticket lines 32-34) is still unresolved.** The Technical note (lines 150-155)
   is marked "proposed default -- confirm" and says "checked by replaying `example`". That wording
   is not in any AC, so leaving out the replay check is not an AC failure. But the developer cannot
   close an open question alone. The lead needs to record a decision. Reviewer recommendation:
   confirm exact function-name equality within the trial's target and drop the per-bucket replay
   check. The CSV `crash_site` is already the extractor's output on that input's own report, so by
   ADR-0005 section 3 process invariance a replay returns the same string. Replay could only catch
   a changed binary or a broken symbolizer, and AFL-011's pre-flight symbolizer check already covers
   both. Then strike the open question and edit the note to match.

Non-blocking:
- `test_dedup.py:109` hardcodes `"scan"`. AC 13 says "equal `toy-2`'s `function` in
  `targets/ground_truth.json`", so read it from there.
- The `sys.path.insert(0, harness/)` import (`test_dedup.py:13`) is acceptable.
- Invariants: no change outside `harness/`, `tests/` and `docs/adr/`, so arm isolation (NFR-2) and
  blind mutation are untouched. Nothing in dedup depends on the clock or the PID. Ordering ties
  break on `first_execs`.

## Re-review (reviewer, 2026-11-14, after bounce 1)
**Verdict: approve -> testing.**

Gates: `ruff check .` clean (whole repo); `mypy src` clean (8 files); `pytest tests/test_dedup.py`
12 passed, 0 skipped (both clang tests ran: real tlv_parser loop and toy-2 two-process run).

Bounce-1 items:
1. Required change 1 (cross-target mis-mapping): fixed. `dedup.py:38-52`: `target: str` is
   required, `funcs` is built only from that target's bugs, and an empty map raises `ValueError`.
   Test `test_dedup.py:55-60`: the same `main` row gives `tlv-1` under `tlv_parser`, `None` under
   `toy_parser`, and `"nope"` raises. Every other test call passes a target. No other caller of
   `bucket_trial` exists yet. ADR-0003:37-40 and 66-67 updated.
2. Required change 2 (open question 4): resolved by lead decision, 2026-11-14 (lines 32-39). The
   Technical note (lines 155-160) matches: exact function-name equality within the target, no
   replay. The rationale holds. `crash_site` was computed during the trial from that input's own
   report, so a later binary change cannot alter a stored key.
3. ADR-0003 -g/CFLAGS sentence: present (0003:53-55). Matches `targets/Makefile:9-10`
   (`CFLAGS ?= -g`; `-g` is not in `override REQUIRED_FLAGS`).
4. ADR-0005 pointer: not done. It is deferred to stop 2 by lead decision, so it is not counted as
   a defect here. ADR-0005:196-198 still says "ADR-0003 is not written yet. AFL-013 writes it and
   must carry this paragraph over". That sentence is now false. The stop-2 edit must replace it
   with a pointer to ADR-0003, or remove the duplicated paragraph.
5. Non-blocking item (hardcoded "scan"): fixed. `test_dedup.py:120-121` reads
   `truth["toy-2"]["function"]`.

ADR-0005 untouched by AFL-013: confirmed. The working tree differs from
a scratch copy of ADR-0005 as of the AFL-011 commit (outside the repo) only at lines 311-312 (AFL-018's section 6 edges hunk).
The `git diff HEAD` hunks are all AFL-011 or AFL-018. The `AFL-013` in the Related line is
unchanged context.

Per AC (all re-verified on the current diff):
| # | AC | Status | Evidence |
|---|----|--------|----------|
| 1 | Source is the event stream | met | `dedup.py:56-64`; `test_dedup.py:30-34` |
| 2 | Key is site only | met | `dedup.py:58`; `test_dedup.py:37-40` |
| 3 | Same site, same bucket | met | `test_dedup.py:30-40` |
| 4 | Different sites, different buckets | met | `test_dedup.py:43-47` |
| 5 | Unique count = number of buckets | met | one bucket per key (`:65-66`); ADR-0003:66-67 |
| 6 | Heuristic named, overcount bias | met | `dedup.py:3-16`; `test_dedup.py:91` |
| 7 | Merge bias in docstring | met | `dedup.py:14-15`; `test_dedup.py:90` |
| 8 | ADR-0003 records FR-6 interpretation | met | 0003:21-40; `test_dedup.py:94-97` |
| 9 | Symbolizer carry-over | [~], ADR-0003 side met | 0003:47-58 has the full paragraph, so the grep check's "contains that content" branch passes. The ADR-0005 side is deferred (lead decision) |
| 10 | Shared extractor, no frame parsing | met | imports only `SENTINELS`; `test_dedup.py:78-88` |
| 11 | Sentinels never merged | met | `dedup.py:66`; `test_dedup.py:63-75` |
| 12 | Every real bucket has a replay input | met | `test_dedup.py:100-111` (real run, `assert bs` non-vacuous) |
| 13 | `crash_site` process-invariant | met | ADR-0003:41-46; `test_dedup.py:114-125` |

Invariants: changes are limited to `harness/`, `tests/` and `docs/adr/0003`, so NFR-2 arm
isolation and blind mutation are untouched. dedup has no clock, PID or RNG dependence. Ties
break on `first_execs`.

Non-blocking:
- The Interfaces block in the Technical notes (line 138) still shows `bucket_trial(trial_dir: Path)`.
  The binding interface is ADR-0003:66, which is correct. The crew lead may want to sync the note.
- `funcs` (`dedup.py:50`) silently keeps the last bug if two bugs of one target share a function.
  PRD section 8 forbids that, but nothing checks it. Consider a check in AFL-016 (mfp) or in
  AFL-011's pre-flight.
- ADR-0003:39 is an over-long line (cosmetic).

For the crew lead at close: AC 9 stays `[~]` until the stop-2 ADR-0005 edit lands. Do not move
this ticket to done with ADR-0005:196-198 still saying ADR-0003 is unwritten, unless the lead
records that explicitly.

## Test (tester, 2026-11-14)
**Verdict: PASS. Stays in testing/.** It is not closable yet: one open item (below) blocks close.

Environment: working tree at HEAD 5032f29 plus uncommitted AFL-013 files. `targets/bin/tlv_parser`
(built 22:03) and `targets/bin/toy_parser` (built 11-12) did not change during testing. No `make` was
running at any pytest run.

Gates: `ruff check .` all checks passed; `mypy src` no issues (8 files); `pytest tests/test_dedup.py -rs`
12 passed, 0 skipped (both clang tests ran).

Per AC (tester's own evidence):
| # | AC | Status | Evidence |
|---|----|--------|----------|
| 1 | Source is the event stream | pass | `test_every_event_counted_only_one_saved` (7 rows, 1 saved, count 7). The mutant that counts only saved rows is killed. A real trial has 521 events in one bucket and 1 saved input. |
| 2 | Key is site only | pass | `test_signal_not_in_key`. The mutant `key = site + signal` is killed. Probe: signals 6 and 11 at `scan` gave one bucket. |
| 3 | Same site, same bucket | pass | as AC 1/2 |
| 4 | Different sites, different buckets | pass | `test_different_sites_different_buckets_sorted_and_mapped`. The unsorted mutant is killed. |
| 5 | Unique count = number of buckets | pass | one `Bucket` per distinct key (`dedup.py:65-66`); ADR-0003:66-67 |
| 6 | Heuristic named, overcount bias | pass | `dedup.py:3-16`; `test_no_frame_parsing_and_docstring_statements` |
| 7 | Merge bias in docstring | pass | `dedup.py:14-15` |
| 8 | ADR-0003 records FR-6 interpretation | pass | ADR-0003:21-40 (first in-target frame, site only, sentinels, mapping); `test_adr_0003_content` |
| 9 | Symbolizer carry-over | [~] (lead decision) | ADR-0003:47-58 contains the paragraph. ADR-0005 side: see open item |
| 10 | Shared extractor, no frame parsing | pass | `dedup.py` imports only `SENTINELS`; no `re`, `#\d`, `0x` patterns; fixture test gives key `main` |
| 11 | Sentinels never merged | pass | `test_sentinels_never_merged`, `test_sentinel_named_like_function_still_unknown`. Mutants "merge sentinels into one bucket" and "drop the sentinel guard" are both killed. |
| 12 | Every real bucket has a replay input | pass | real-run test; 2 tlv_parser trials (below) each have `example=crashes/000000.bin`, which exists. The probe confirms the earliest saved row is chosen (rows saved 000001 then 000002 give 000001). |
| 13 | `crash_site` process-invariant | pass | `test_crash_site_process_invariant`, plus the probe below on all 4 planted bugs |

Experimental validity (dedup):
- **Ground truth recovered (all 4 planted bugs).** Each trigger (toy-1 `BUGa`, toy-2 `!aaa`, tlv-1 and
  tlv-2 from `targets/triggers.json`) was run in 2 separate processes through `Executor`, with distinct
  PIDs each time. Results: `check/check`, `scan/scan`, `main/main`, `parse_ext/parse_ext`. Each equals its
  `ground_truth.json` `function`. No site string contains `0x`, `/` or the PID. `bucket_trial(dir, target)`
  maps each pair to one bucket with the right `bug_id` and count 2.
- **Per-target mapping.** A `main` row maps to `tlv-1` under `tlv_parser`, to `None` under `toy_parser`, and
  an unknown target raises `ValueError`. The mutants "target ignored" and "no raise" are killed. No target
  in the current `ground_truth.json` has two bugs in the same function.
- **Reproducibility.** Two `fast` trials on tlv_parser with seed 7 were both stopped by the 120 s cap, at
  execs 1374 and 1289. Their `crash_events.csv` rows up to exec 1289 are identical apart from
  `elapsed_s` (486 rows), and the saved inputs match byte for byte. The buckets agree on key, first_execs
  (2), example and bug_id. Count differs only through where the time cap stopped each run (ADR-0005).
- **Honest bucketing.** Biases are disclosed in the docstring and ADR-0003. Sentinels are counted as
  unknown, never credited to a bug. A header-only CSV gives `[]`.
- **Mutation check.** 8 hand mutants were run against the 10 non-clang tests; 7 were killed.

Findings (non-blocking):
1. Test gap: no test pins "the **earliest** saved" for `Bucket.example`. The mutant "last saved wins"
   survives, because the only multi-row test has a single saved row. The code is correct (direct probe
   above), and the AC's own stated test passes. Suggested follow-up: a two-saved-rows assertion.
2. Still unchecked, carried from review: two bugs in one function within a target would silently keep
   the last one (`dedup.py:50`). This is not the case today. It belongs in AFL-011 pre-flight or AFL-016.
3. Stale note: the Technical-notes interface (`bucket_trial(trial_dir: Path)`) still omits `target`.
   ADR-0003:66 is the binding interface and is correct.

**Open item, blocks close:** ADR-0005:196-198 still says "ADR-0003 is not written yet. AFL-013 writes it
and must carry this paragraph over". That is now false. The fix is deferred to stop 2 by lead decision;
the tester did not edit ADR-0005. The crew lead must not move this ticket to done until that pointer
lands, unless the lead records an explicit exception.

## Log
- 2026-11-07 — created (req-engineer)
- 2026-11-07 — review fix: dedup.py imports AFL-007's shared crash-site function from src/fuzzer/ and has no extraction logic of its own (replaces the top-3-frame hash note); sentinels "unsymbolized"/"no_target_frame" carried through as unknown-crash buckets, never merged with real-site buckets; tests added for both; depends_on += AFL-007 (real dependency via the shared function; INDEX row needs the same change) (human decision) (req-engineer)
- 2026-11-07 — review fix: dedup buckets every event in crash_events.csv by `crash_site` (saved inputs for replay only; AC1 reworded, stale "AC1 wording" note removed, saving open question resolved); key is site only, no signal, with test; ADR-0003 AC (first in-target frame = top-of-stack); docstring AC for the same-function merge bias; `"no_stack"` sentinel added, each sentinel its own unknown bucket; `Bucket.example: Path | None` from the `saved` column, non-None for every non-sentinel bucket, tested; shared-extractor AC reworded to use the column verbatim; depends_on `[AFL-003, AFL-007]` confirmed (human decision) (req-engineer)
- 2026-11-12 — added AC "ADR-0003 carries over the ADR-0005 §3 symbolizer note": ADR-0003 either moves in ADR-0005 §3's "A missing symbolizer gives `no_target_frame`" paragraph or references ADR-0005 §3 explicitly. The matching pre-run symbolizer check is in AFL-011 (human decision, 2026-11-12) (req-engineer)
- 2026-11-12 — added AC "`crash_site` is process-invariant", enforcing ADR-0005 §3 ("`crash_site` is replay-safe"): toy-2's `b"!aaa"` run in two separate processes gives the identical `crash_site` (`"scan"`), with no PID, no `0x` address and no path. No existing AC was equivalent (the "Shared crash-site extractor" AC tests one captured fixture report, not two processes), so nothing was reconciled or replaced (human decision, 2026-11-12) (req-engineer)
- 2026-11-14 — developer: implemented `harness/dedup.py` (`Bucket`, `bucket_trial(trial_dir, target=None, ground_truth=GROUND_TRUTH)`; imports only `SENTINELS` from `fuzzer.fuzzer`, no frame parsing), `docs/adr/0003-crash-site-dedup.md`, `tests/test_dedup.py` (11 tests: N events/1 saved, signal not in key, distinct sites, sentinels x3 + mixed, shared-extractor fixture key, docstring/grep checks, ADR content, real tlv_parser run with existing `example` per real bucket, toy-2 process invariance). All ACs met except one part: the ADR-0005 section 3 symbolizer paragraph is copied into ADR-0003 but the matching pointer/removal in ADR-0005 is PENDING (another agent is editing ADR-0005; ADR-0003 is the carry-over and satisfies the "contains that content" alternative). Bug mapping: site == ground_truth `function` (file implied by target); replay-check of `example` not implemented (needs binary; mapping is exact-name). Gates: ruff clean on harness/ and test_dedup.py; mypy src clean; test_dedup 11 passed. Repo-wide: pre-existing/unrelated ruff E/RUF hits in other tests, and test_toy_parser::test_ground_truth_and_source_docs fails because targets/ground_truth.json now has tlv entries (concurrent targets/ edit).
- 2026-11-14 — reviewer: changes requested -> in-progress. All 13 ACs met; the symbolizer carry-over stays [~] pending the ADR-0005 pointer. Required: (1) `target` required and unknown target raises, because the `target=None` default maps any target's `main` crash to tlv-1 (reproduced); (2) the lead resolves open question 4 (mapping rule; replay-of-`example` check recommended dropped as redundant with process invariance + AFL-011 pre-flight). Gates green on scope (ruff, mypy src, test_dedup 11/11) (reviewer)
- 2026-11-14 — developer: bounce 1 fixed. `bucket_trial(trial_dir, target, ground_truth=...)` now requires `target`, looks up bug_id only in that target's bugs, raises ValueError for an unknown target (new test: `main` -> tlv-1 under tlv_parser, None under toy_parser, unknown raises); OQ4 resolved and note edited; ADR-0003 updated (target required, `-g`/CFLAGS fact added); test no longer hardcodes "scan". ADR-0005 pointer queued for stop 2 (lead decision, 2026-11-14): ADR-0005 not edited; carry-over AC stays [~].
- 2026-11-14 — reviewer: re-review after bounce 1, approve -> testing. Both required changes fixed (target required, per-target lookup, unknown target raises, with test; OQ4 resolved by lead decision); -g/CFLAGS sentence present; scan test reads ground_truth.json. ADR-0005 confirmed untouched by AFL-013 (only the AFL-011 and AFL-018 hunks). AC 9 stays [~] until the stop-2 ADR-0005 pointer replaces the stale 'ADR-0003 is not written yet' at 0005:196-198. Gates: ruff . clean, mypy src clean, test_dedup 12/12, 0 skipped (reviewer)
- 2026-11-14 — tester: PASS, stays in testing. Gates: ruff . clean, mypy src clean, test_dedup 12/12, 0 skipped. All 4 planted bugs recovered (process-invariant site == ground-truth function, correct per-target bug_id). Same-seed event stream reproducible (identical prefix through exec 1289). Mutants: 7/8 killed; the 'last saved' survivor is a non-blocking test gap. AC 9 stays [~]. Close is blocked on the stop-2 ADR-0005:196-198 pointer (tester)
- 2026-11-15 — DoD verified, moved to done (crew-lead). Symbolizer carry-over AC flipped [~] -> [x]: ADR-0003:47-58 holds the full "A missing symbolizer gives `no_target_frame`" paragraph (moved here from ADR-0005 section 3), and the ADR-0005 pointer has landed: ADR-0005:196-200 no longer says "ADR-0003 is not written yet" and now points to that ADR-0003 Decision bullet as the authoritative home, which is what the reviewer (lines 257-260, 298-300) and tester (lines 355-358) asked for (lead decision, 2026-11-15). All 13 ACs ticked on reviewer APPROVE and tester PASS evidence. Non-blocking notes left open: no test pins "earliest saved" for `Bucket.example`; a duplicate function within one target is unchecked (`dedup.py:50`, for AFL-011 pre-flight or AFL-016); the Technical-notes interface omits `target` (ADR-0003:66 is binding). Commit must reference AFL-013 (human's step).
