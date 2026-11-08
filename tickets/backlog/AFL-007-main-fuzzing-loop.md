---
id: AFL-007
title: Main fuzzing loop (wire everything)
requirement: FR-1..5, FR-8 (metrics output), NFR-1, NFR-5
paper_ref: AFL whitepaper (fuzzing loop); AFLFast § power schedules (energy per seed); Klees § performance measures (crash counting, time-to-first-crash)
module: src/fuzzer/fuzzer.py; docs/adr/0005-* (architect, new)
depends_on: [AFL-002, AFL-003, AFL-004, AFL-005, AFL-006, AFL-009]
status: backlog
owner: developer
---

## Goal
Connect coverage (FR-1), executor (FR-2), corpus (FR-3), mutator (FR-4) and
schedule (FR-5) into one greybox loop: pick a seed, ask the schedule for its
energy, generate and run that many blind mutants, keep the ones with new
coverage. This is the M1 baseline fuzzer.

Open questions — all resolved (human, 2026-11-07):
- ~~FR-8 metric logging has no owner.~~ **Resolved:** this ticket owns the FR-8
  metrics output (see ACs "Metrics output (FR-8)" and "Crash event stream").
- ~~How does the loop stop?~~ **Resolved:** on `seconds` of wall-clock or on
  `max_execs`, whichever comes first.
- ~~What does "reproducible" mean under a wall-clock budget?~~ **Resolved:** replay is
  guaranteed on the exec index (same seed ⇒ same exec-indexed stream; only
  wall-clock fields vary). Exact replay holds when the run stops on `max_execs`.
  Recorded in ADR-0005 (architect).
- ~~NFR-5 integration test needs AFL-009.~~ **Resolved:** AFL-009 added to
  `depends_on`.

## Acceptance criteria
- [ ] Each iteration selects a seed from the corpus, obtains its energy from
      `assign_energy(seed, corpus)`, and generates and executes that many mutated
      candidates.
- [ ] Clean candidates are passed to `corpus.observe()`, which retains iff ≥1 new
      edge (FR-1, FR-3; ADR-0004 §2).
- [ ] Every clean execution is passed to `corpus.observe(cand, r)`, which updates
      path frequency f(i) on every clean exec, retained or not (ADR-0004 §2). The
      loop never writes f(i) itself.
- [ ] After a seed's whole energy has been spent, the loop calls
      `corpus.mark_fuzzed(seed)`, the only place `times_selected` (s(i)) changes,
      so the first `assign_energy` call for a seed sees s(i) = 0 (ADR-0004 §3).
- [ ] The loop asserts `energy >= 1` after every `assign_energy` call; a violation
      raises (e.g. `ValueError`) rather than spinning or skipping the seed
      (ADR-0004 §8; ≥1 rule confirmed (human, 2026-11-07; ADR-0004 §8)).
      Test: run the loop with a stub schedule returning 0 and expect the raise.
- [ ] **Initial corpus:** exactly the files in `cfg.seeds_dir`
      (`targets/seeds/<target>/S0`, ADR-0004 §6). Each is executed and its result
      passed to `corpus.observe()` (not routed by outcome, so a crashing or
      hanging S0 makes `observe()` raise). No `b""` fallback; a missing or empty
      seeds dir raises before fuzzing starts.
- [ ] **Exec counting (human decision, 2026-11-07).** `execs` means the total
      number of target executions in the run. Every initial-corpus execution counts:
      the S0 execution is exec 1, both toward `cfg.max_execs` and in the `execs`
      column of `metrics.csv` and `crash_events.csv`. Mutated candidates are execs
      2, 3, …. Exec indices are 1-based and gap-free. Test: with a one-file seeds dir
      (S0 only), the first metrics row after S0 has `execs == 1`, and the first
      candidate execution is recorded as `execs == 2`.
- [ ] **Crash storage (human, 2026-11-07; save rule widened, human decision,
      2026-11-07).** A `"crash"` input is saved to `<out>/crashes/` if and only if
      its `coverage.path_id` is new among crashes seen so far in this run **or** its
      `crash_site` (including a sentinel value) is new among crashes seen so far in
      this run. Reason: replay of a bucket's saved input is how AFL-013 checks the
      bucket's mapping to a planted bug, so the first crash at every site must be
      saved even when its `path_id` was already seen at a different site.
      Consequence: the first crash event of every distinct `crash_site` is always
      saved. Tests: (a) two crashes with the same `path_id` and the same
      `crash_site` save one file; (b) a crash with a new `path_id` saves a second;
      (c) a crash whose `path_id` was already seen on an earlier crash at a
      different `crash_site`, but whose own `crash_site` is new, is saved.
- [ ] **Crash events link to saved inputs (human decision, 2026-11-07).** The
      `saved` column of `crash_events.csv` holds the saved input's path relative to
      `<out>` (e.g. `crashes/000003.bin`) when that event's input was saved, and is
      empty otherwise. AFL-013 uses it to set each bucket's replay example. Test:
      every non-empty `saved` value names an existing file under `<out>/crashes/`
      whose sibling `.json` has the same `execs` as the row; for every distinct
      `crash_site` in `crash_events.csv`, the earliest row with that site has a
      non-empty `saved`.
- [ ] **Crash event stream (human, 2026-11-07).** Every crash event is recorded in
      the metrics output whether or not its input was saved, with at least:
      timestamp (`elapsed_s`), exec count (`execs`), `signal`, and crash site
      (first in-target stack frame, the same definition AFL-013/AFL-016 use). Test:
      N crashes sharing one `path_id` and one `crash_site` yield N crash-event
      records and 1 saved file. Downstream rules this stream exists for (not
      computed here): per-bug time-to-first-crash is the first crash event at that
      bug's site; reported crash counts come from AFL-013's site dedup of this
      stream, never from the storage rule or the number of saved files.
- [ ] **Crash-site extraction skips runtime frames (human decision, 2026-11-07).**
      The site-extraction function in `src/fuzzer/` (the one AFL-013's dedup.py
      imports, see Technical notes) skips ASan runtime/interceptor frames
      (`__asan_*`, `__interceptor_*`, frames in the sanitizer runtime library) and
      libc frames, and returns the first frame whose source file belongs to the
      target's own source. Reason: in tlv_parser's overflow report, frame #0 is
      ASan's `memcpy` interceptor (`__asan_memcpy`), not target code.
- [ ] **Real-report fixture test (human decision, 2026-11-07).** A unit test runs
      the extraction function on a captured, symbolized ASan report from
      tlv_parser's `memcpy` overflow. The report is captured from a real build made
      with the repo's `targets/Makefile` (not hand-written) and committed under
      `tests/fixtures/` (e.g. `tests/fixtures/tlv_parser_asan_memcpy.txt`), with a
      one-line note of the build command and commit it came from. The test asserts
      the returned site is tlv_parser's own function (`main` in `tlv_parser.c`, per
      AFL-010), not the interceptor. **Source (human decision, 2026-11-07):** the
      fixture is captured from today's `targets/tlv_parser.c`, so AFL-010 is not a
      dependency of this ticket. The fixture file records the source commit it was
      captured from.
- [ ] **Fixture staleness tripwire (human decision, 2026-11-07).** An integration
      test builds `targets/bin/tlv_parser` with `targets/Makefile`, runs the
      overflow trigger through `Executor`, and asserts that the live ASan report
      parses (via the same extraction function) to the same crash site as the
      committed `tests/fixtures/` report. The fixture serves the fast unit tests;
      this integration test makes fixture drift (e.g. after AFL-010 changes
      tlv_parser) fail a test.
- [ ] **Extraction fails visibly: three sentinels, never empty (human decision,
      2026-11-07; `"no_stack"` added, human decision, 2026-11-07).** The function
      never returns an empty string. It returns `"no_stack"` when stderr contains no
      ASan stack frames at all (e.g. a SIGSEGV with empty stderr; after AFL-018, also
      signals ASan may not intercept, such as SIGILL depending on `handle_sigill`),
      `"unsymbolized"` when stack frames are present but carry no function names
      (addresses only), and `"no_target_frame"` when the stack is symbolized but no
      frame comes from target source. Tests: an empty stderr returns `"no_stack"`;
      an addresses-only report returns `"unsymbolized"`; a symbolized report with
      only runtime/libc frames returns `"no_target_frame"`; none returns `""`.
- [ ] **Sentinels are counted, never dropped (human decision, 2026-11-07).** A crash
      whose site is `"no_stack"`, `"unsymbolized"` or `"no_target_frame"` is still
      written as a row of `crash_events.csv` with that sentinel in `crash_site`, and
      counted in `metrics.csv`'s `crash_events`. Tests: a stubbed crash with an
      addresses-only stderr yields one `crash_events.csv` row with
      `crash_site == "unsymbolized"`; a stubbed SIGSEGV crash with empty stderr
      yields one row with `crash_site == "no_stack"`.
- [ ] **Metrics output (FR-8, human, 2026-11-07).** This ticket owns and writes the
      FR-8 per-run metrics files in the format fixed in Technical notes
      ("FR-8 metrics format"), which AFL-011/012/013/014 build against.
- [ ] **Stopping (human, 2026-11-07).** The loop stops when `cfg.seconds` of
      wall-clock is spent or when `cfg.max_execs` executions have run (if set),
      whichever comes first. The budget is checked on every exec, and `max_execs`
      counts every target execution including S0 (AC "Exec counting"). Test: with
      a one-file seeds dir (S0 only), `max_execs = M` (M ≥ 2) and a large `seconds`,
      exactly M target executions run, i.e. the S0 execution plus exactly M − 1
      candidate executions, and the final `metrics.csv` row has `execs == M`
      (count executor `run()` calls with a stubbed or wrapped executor).
- [ ] **Exec-index replay (human, 2026-11-07; ADR-0005).** Two runs with the same
      `cfg.seed` that stop on `max_execs` produce identical metrics streams and
      crash-event streams in every column except wall-clock fields (`elapsed_s`).
      The exec index is the `execs` value defined in AC "Exec counting" (S0 = exec
      1), so the streams match row by row from the S0 execution onward. Timeouts
      are the one disclosed timing-dependent exception. Test: run twice on
      toy_parser (or a stubbed executor) with fixed seed and `max_execs`; compare
      streams with `elapsed_s` dropped; both final rows have `execs == max_execs`.
- [ ] **ADR-0005 written (architect).** `docs/adr/0005-*.md` records the stopping
      rule and the exec-index replay guarantee (including the timeout exception)
      before this ticket leaves review.
- [ ] **NFR-2:** the schedule is chosen by one parameter, and fuzzer.py has no
      other branch on it. The two arms differ only inside schedule.py.
- [ ] **NFR-1:** fuzzer.py constructs exactly one `random.Random(cfg.seed)` per
      run and passes that same object to every `mutator.mutate` call; no other RNG
      is constructed or used in the loop. Test: with a fixed exec-count/iteration
      stop (or a stubbed executor), two runs with the same `cfg.seed` produce
      identical candidate sequences, and runs with different seeds differ —
      proving the trial seed assigned by AFL-011 (`base_seed + i`) reaches the
      mutations.
- [ ] **Blind mutation:** the loop never passes coverage data to the mutator.
- [ ] Integration test: with UNIFORM, the fuzzer finds the toy_parser planted bug
      within a stated budget (NFR-5, M1).
- [ ] **Startup guard (from AFL-002/003).** If the very first execution of the
      first seed yields zero edges, abort loudly with "no instrumentation detected"
      — the target was not built with coverage and the whole run is worthless.
      Runtime complement to the build-time tripwire in `tests/test_coverage.py`.
      Test: a target built without trace-pc-guard makes `run()` raise before any
      metrics are written.

## Technical notes (architect)
- **Interfaces (`fuzzer.py`).** cli.py (AFL-008) consumes these, and run_campaign.py
  (AFL-011) reaches them through the CLI:
  ```python
  @dataclass(frozen=True)
  class FuzzConfig:
      target: Path
      schedule: str               # "uniform" | "fast"
      seconds: float
      seed: int
      out_dir: Path
      seeds_dir: Path             # required; holds S0 (ADR-0004 §6). cli.py (AFL-008) resolves the default.
      max_execs: int | None = None
      timeout_s: float = 1.0

  def run(cfg: FuzzConfig) -> None: ...
  ```
- **Loop.** `rng = random.Random(cfg.seed)` is created once, here. The only use of
  `cfg.schedule` in fuzzer.py is `assign_energy = schedule.SCHEDULES[cfg.schedule]`
  (per ADR-0004 §8). Then, until the budget is spent:
  `seed = corpus.select()`, `energy = assign_energy(seed, corpus)`, and for each unit
  of energy: `cand = mutator.mutate(seed.data, rng, [s.data for s in corpus.seeds])`,
  `r = executor.run(cand)`, then branch on `r.outcome` (AFL-003 three-outcome
  model): `"crash"` → record the crash event, save per the storage rule; `"hang"` → count it in `hangs` only (never a
  crash, never in the corpus); `"clean"` → `corpus.observe(cand, r)`. After the energy is spent,
  `corpus.mark_fuzzed(seed)`. Check the budget on every exec, not once per seed. Close
  the executor (which unlinks the shm) in `finally`.
- Crashes and hangs never enter the corpus: only clean results go to
  `corpus.observe()`, which raises `ValueError` on any non-clean result
  (confirmed (human, 2026-11-07; ADR-0004 §2)). The mutator only ever sees bytes.
- **Stopping and reproducibility** (confirmed, human, 2026-11-07; → ADR-0005,
  architect writes it): stop at `seconds` of wall-clock or at `max_execs`, whichever
  comes first. The same seed gives the same candidate sequence exec by exec. So the
  exec-indexed stream (execs, edges, corpus size, crash events) is reproducible and
  only `elapsed_s` varies. Exact replay is guaranteed when the run stops on
  `max_execs`. Timeouts are the one timing-dependent exception. AFL-011's
  reproducibility AC is worded to match.
- **FR-8 metrics format** (owned and implemented by this ticket, human,
  2026-11-07). Fixed here so AFL-011/012/013/014 can build against it.
  - `<out>/metrics.csv`: one row on every change to edges, corpus size or crash
    events, plus a final row. Columns:
    `elapsed_s,execs,edges,corpus_size,distinct_path_ids,crash_events,crashes_saved,hangs`
    (`distinct_path_ids` is required by AFL-011's pilot rule).
  - `<out>/crash_events.csv`: one row per crash event, saved or not. Columns:
    `elapsed_s,execs,signal,crash_site,path_id,saved`. `saved` is the saved
    input's path relative to `<out>` (`crashes/<n:06d>.bin`) or empty if the
    event's input was not saved. This is the only link from an event to its saved
    input; AFL-013 reads it.
  - `<out>/crashes/<n:06d>.bin` + `<n:06d>.json` holding
    `{elapsed_s, execs, signal, exit_status, path_id, crash_site, stderr}`, only
    for crashes kept by the storage rule below.
  - `<out>/queue/` is written by the corpus. `<out>/run.json` is written by cli.py
    (AFL-008).
- **Crash site in the event stream.** fuzzer.py never imports `harness/`. The
  site-extraction function (first in-target ASan stack frame, ADR-0002
  `symbolize=1`) therefore lives in `src/fuzzer/` and AFL-013's dedup.py imports
  that same function, so the stream's `crash_site` and dedup's buckets cannot
  disagree.
- **Crash storage rule** (confirmed, human, 2026-11-07; widened, human decision,
  2026-11-07): save a crash if and only if its `path_id` is new among crashes
  **or** its `crash_site` (sentinels included) is new among crashes. Keep two sets
  in the loop, seen crash `path_id`s and seen crash sites. tlv_parser crashes on
  almost any second byte > 64, so saving every crash would mean tens of thousands
  of files per trial; the site clause adds about one file per planted bug plus
  sentinels. The site clause guarantees every AFL-013 bucket has a saved input to
  replay. Storage is for reproducing inputs only: crash counts and per-bug
  time-to-first-crash come from `crash_events.csv` via AFL-013's site dedup, never
  from the number of saved files.
- **Crash-site sentinels:** `"no_stack"` (no ASan frames in stderr),
  `"unsymbolized"` (frames, no function names), `"no_target_frame"` (symbolized,
  no target frame). The extractor returns exactly one site string per crash.
- **Seed selection** is fixed round-robin via `corpus.select()` and identical in
  both arms; fuzzer.py adds no selection logic. AFLFast's search strategy is
  omitted and disclosed as a deviation (confirmed (human, 2026-11-07; ADR-0004
  §4–5)).
- **Integration test:** use `targets/bin/toy_parser` (AFL-009, now in `depends_on`). Run with a fixed seed, `max_execs` (e.g. 200_000) and a
  large `seconds`, so the test is deterministic rather than time-based.

## Test approach (tester)
Integration test on toy_parser under a fixed seed. Review/grep check that
fuzzer.py contains no schedule-specific branch and passes no coverage to the
mutator. Unit tests with a stubbed executor for the crash save rule (cases
(a)-(c)), the `saved` link column, and each of the three crash-site sentinels.

## Log
- 2026-11-07 — created (req-engineer)
- 2026-11-07 — startup "no instrumentation detected" guard moved here from AFL-003
  as an AC (human decision). Loop note: branch on `r.outcome` (AFL-003 three-outcome
  model): `"crash"` → save, `"hang"` → count in `hangs` only, `"clean"` →
  `corpus.observe` (architect)
- 2026-11-07 — stale-note sweep: Technical notes "Loop" rewritten from
  `r.crashed`/`r.timed_out` to branch on `r.outcome`, matching the entry above
  (req-engineer)
- 2026-11-07 — aligned with ADR-0004 (req-engineer)
- 2026-11-07 — recorded human decision: energy ≥ 1 confirmed; loop asserts it and raises on violation, tested with a stub schedule returning 0 (req-engineer)
- 2026-11-07 — NFR-1 AC tightened: one Random(cfg.seed) reaches every mutate() call, tested (req-engineer)
- 2026-11-07 — batch grooming: stop on `seconds` or `max_execs` with exec-index replay (ADR-0005, architect); crash saved iff `path_id` new among crashes; every crash event recorded (elapsed_s, execs, signal, crash site) whether saved or not, per-bug TTFC from first event at the bug's site, counts from AFL-013 site dedup only; this ticket owns FR-8 metrics output; depends_on += AFL-009; open questions resolved (human decision) (req-engineer)
- 2026-11-07 — review fix: S0 execution is exec 1 (counts toward `max_execs` and the `execs` column; `execs` = total target executions); stopping test reworded to S0 + M − 1 candidates, replay AC anchored on that exec index; crash-site extraction ACs added (skip ASan/libc frames, real tlv_parser ASan fixture under tests/fixtures/, sentinels "unsymbolized"/"no_target_frame", never empty, counted in crash_events.csv) (human decision) (req-engineer)
- 2026-11-07 — review fix: crash-site fixture captured from today's targets/tlv_parser.c (AFL-010 not added to depends_on), fixture records its source commit; added staleness-tripwire AC: integration test builds/runs tlv_parser and asserts the live ASan report parses to the fixture's crash site (human decision) (req-engineer)
- 2026-11-07 — review fix: crash save rule widened to "path_id new among crashes OR crash_site new" so every dedup bucket has a replayable input, test (c) added; `crash_events.csv` `saved` column defined as the saved file's path relative to `<out>` (empty if unsaved) with a link test; third sentinel `"no_stack"` (no ASan frames in stderr) added, counted never dropped, with tests (human decision) (req-engineer)
