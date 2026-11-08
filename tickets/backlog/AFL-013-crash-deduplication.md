---
id: AFL-013
title: Crash de-duplication (crash-site bucketing)
requirement: FR-6
paper_ref: Klees § performance measures (crash de-duplication overcounts; ground truth)
module: harness/dedup.py
depends_on: [AFL-003, AFL-007]
status: backlog
owner: developer
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
- PRD §8(c) measures time-to-first-crash **per planted bug**. That needs a map
  from bucket to planted bug (ground truth). The PRD does not say how to build
  that map. (Proposed default in Technical notes; still to confirm.)

## Acceptance criteria
- [ ] **Source is the event stream (human decision, 2026-11-07).** `bucket_trial`
      reads `<trial>/crash_events.csv` (AFL-007) and buckets **every** crash event
      in it by its `crash_site` column. Saved crash inputs under `<trial>/crashes/`
      exist only for replay (checking a bucket's mapping to a planted bug); they
      are never counted and never used to form buckets. Test: a trial with N
      `crash_events.csv` rows at one site, of which only 1 has a saved input,
      yields one bucket with `count == N`.
- [ ] **Bucket key is the crash site only (human decision, 2026-11-07).** The
      bucket key is the `crash_site` value; the signal is not part of it. Test: two
      events with the same `crash_site` and different `signal` land in one bucket.
- [ ] Two crash events that hit the same crash site land in the same bucket.
- [ ] Crash events at different crash sites land in different buckets.
- [ ] The unique-crash count reported equals the number of buckets.
- [ ] The heuristic is documented: named in the module docstring or README, with
      its known overcounting bias acknowledged (PRD §8, Klees).
- [ ] **Known merge bias in the docstring (human decision, 2026-11-07).**
      `harness/dedup.py`'s module docstring states that two bugs in one function
      merge into one bucket (site = function), and that this is why every planted
      bug sits in its own function. Test: the docstring contains this statement
      (review/grep check).
- [ ] **ADR-0003 records the FR-6 interpretation (human decision, 2026-11-07).**
      This ticket writes `docs/adr/0003-*.md`, which records that FR-6's
      "PC / top-of-stack" is interpreted as the first in-target stack frame (the
      AFL-007 shared extractor), that the key is the site only (no signal), and the
      sentinel handling below. Present before this ticket leaves review.
- [ ] **Shared crash-site extractor (human decision, 2026-11-07; reworded for the
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
- [ ] **Sentinels carried through, never merged (human decision, 2026-11-07).**
      Each of the three AFL-007 sentinels (`"no_stack"`, `"unsymbolized"`,
      `"no_target_frame"`) gets its own unknown-crash bucket (`bug_id=None`),
      never merged with a real crash-site bucket or with another sentinel's
      bucket. Tests: a trial with one crash at a real site and one addresses-only
      crash at the same planted bug yields two buckets, one with the real site and
      one `"unsymbolized"` bucket reported as unknown; a trial with one event of
      each sentinel yields three separate unknown buckets.
- [ ] **Every real bucket has a replay input (human decision, 2026-11-07).**
      `Bucket.example` is `Path | None`: the `saved` path (AFL-007's
      `crash_events.csv` column, relative to the trial dir) of the earliest event
      in the bucket with a non-empty `saved`, else `None`. Test: on a trial
      directory written by AFL-007's loop (e.g. a short `max_execs` run on
      tlv_parser), `example` is not `None` and the file exists for every
      non-sentinel bucket.

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
- **Mapping to planted bugs** (proposed default — confirm): a bucket maps to bug B
  when its crash site's function and file match B in
  `targets/ground_truth.json` (AFL-009/010), checked by replaying `example`.
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

## Log
- 2026-11-07 — created (req-engineer)
- 2026-11-07 — review fix: dedup.py imports AFL-007's shared crash-site function from src/fuzzer/ and has no extraction logic of its own (replaces the top-3-frame hash note); sentinels "unsymbolized"/"no_target_frame" carried through as unknown-crash buckets, never merged with real-site buckets; tests added for both; depends_on += AFL-007 (real dependency via the shared function; INDEX row needs the same change) (human decision) (req-engineer)
- 2026-11-07 — review fix: dedup buckets every event in crash_events.csv by `crash_site` (saved inputs for replay only; AC1 reworded, stale "AC1 wording" note removed, saving open question resolved); key is site only, no signal, with test; ADR-0003 AC (first in-target frame = top-of-stack); docstring AC for the same-function merge bias; `"no_stack"` sentinel added, each sentinel its own unknown bucket; `Bucket.example: Path | None` from the `saved` column, non-None for every non-sentinel bucket, tested; shared-extractor AC reworded to use the column verbatim; depends_on `[AFL-003, AFL-007]` confirmed (human decision) (req-engineer)
