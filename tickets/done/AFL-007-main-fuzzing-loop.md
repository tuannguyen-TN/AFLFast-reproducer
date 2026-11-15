---
id: AFL-007
title: Main fuzzing loop (wire everything)
requirement: FR-1..5, FR-8 (metrics output), NFR-1, NFR-5
paper_ref: AFL whitepaper (fuzzing loop); AFLFast § power schedules (energy per seed); Klees § performance measures (crash counting, time-to-first-crash)
module: src/fuzzer/fuzzer.py; docs/adr/0005-* (architect, new)
depends_on: [AFL-002, AFL-003, AFL-004, AFL-005, AFL-006, AFL-009]
status: done
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
- [x] Each iteration selects a seed from the corpus, obtains its energy from
      `assign_energy(seed, corpus)`, and generates and executes that many mutated
      candidates.
- [x] Clean candidates are passed to `corpus.observe()`, which retains iff ≥1 new
      edge (FR-1, FR-3; ADR-0004 §2).
- [x] Every clean execution is passed to `corpus.observe(cand, r)`, which updates
      path frequency f(i) on every clean exec, retained or not (ADR-0004 §2). The
      loop never writes f(i) itself.
- [x] After a seed's whole energy has been spent, the loop calls
      `corpus.mark_fuzzed(seed)`, the only place `times_selected` (s(i)) changes,
      so the first `assign_energy` call for a seed sees s(i) = 0 (ADR-0004 §3).
- [x] The loop asserts `energy >= 1` after every `assign_energy` call; a violation
      raises (e.g. `ValueError`) rather than spinning or skipping the seed
      (ADR-0004 §8; ≥1 rule confirmed (human, 2026-11-07; ADR-0004 §8)).
      Test: run the loop with a stub schedule returning 0 and expect the raise.
- [x] **Initial corpus:** exactly the seed files in `cfg.seeds_dir`
      (`targets/seeds/<target>/S0`, ADR-0004 §6), as defined by AC "Seed files and
      load order". Each is executed and its result
      passed to `corpus.observe()` (not routed by outcome, so a crashing or
      hanging S0 makes `observe()` raise). No `b""` fallback; a missing seeds dir,
      or one with no seed file, raises before fuzzing starts.
- [x] **Seed files and load order (human decision, 2026-11-12; ADR-0005 §1).** The
      seed files of a directory are its regular files whose names do not start
      with `.`, in `sorted()` filename order (Python sorts `str` by code point, so
      the order does not depend on the locale). One function in `fuzzer.py`
      computes this list; `run()` loads exactly that list, and cli.py (AFL-008,
      `run.json`) and run_campaign.py (AFL-011, pre-flight) call the same function,
      so no second copy of the rule exists. Reason: Finder writes `.DS_Store` into
      any directory it opens; it is untracked (gitignored once AFL-015 lands), so
      the dirty-tree check never sees it, and without this rule it would become a
      second initial seed. Tests: a seeds dir holding `S0` and `.DS_Store` loads
      only `S0` (one initial execution); a dir holding `b` and `a` loads `a` then
      `b`; a dir holding only `.DS_Store` raises before any execution. Only regular files are
      seeds: a subdirectory, or any other non-file entry, is never read as a seed
      (human decision, 2026-11-12). Tests: a dir holding `S0` and a subdirectory `sub/`
      (containing a file) loads only `S0`; a dir holding only a subdirectory raises
      before any execution.
- [x] **Exec counting (human decision, 2026-11-07).** `execs` means the total
      number of target executions in the run. Every initial-corpus execution counts:
      the S0 execution is exec 1, both toward `cfg.max_execs` and in the `execs`
      column of `metrics.csv` and `crash_events.csv`. Mutated candidates are execs
      2, 3, …. Exec indices are 1-based and gap-free. Test: with a one-file seeds dir
      (S0 only), the first metrics row after S0 has `execs == 1`, and the first
      candidate execution is recorded as `execs == 2`.
- [x] **Crash storage (human, 2026-11-07; save rule widened, human decision,
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
- [x] **Crash events link to saved inputs (human decision, 2026-11-07).** The
      `saved` column of `crash_events.csv` holds the saved input's path relative to
      `<out>` (e.g. `crashes/000003.bin`) when that event's input was saved, and is
      empty otherwise. AFL-013 uses it to set each bucket's replay example. Test:
      every non-empty `saved` value names an existing file under `<out>/crashes/`
      whose sibling `.json` has the same `execs` as the row; for every distinct
      `crash_site` in `crash_events.csv`, the earliest row with that site has a
      non-empty `saved`.
- [x] **Crash event stream (human, 2026-11-07).** Every crash event is recorded in
      the metrics output whether or not its input was saved, with at least:
      timestamp (`elapsed_s`), exec count (`execs`), `signal`, and crash site
      (first in-target stack frame, the same definition AFL-013/AFL-016 use). Test:
      N crashes sharing one `path_id` and one `crash_site` yield N crash-event
      records and 1 saved file. Downstream rules this stream exists for (not
      computed here): per-bug time-to-first-crash is the first crash event at that
      bug's site; reported crash counts come from AFL-013's site dedup of this
      stream, never from the storage rule or the number of saved files.
- [x] **Crash-site extraction skips runtime frames (human decision, 2026-11-07).**
      The site-extraction function in `src/fuzzer/` (the one AFL-013's dedup.py
      imports, see Technical notes) skips ASan runtime/interceptor frames
      (`__asan_*`, `__interceptor_*`, frames in the sanitizer runtime library) and
      libc frames, and returns the first frame whose source file belongs to the
      target's own source. Reason: in tlv_parser's overflow report, frame #0 is
      ASan's `memcpy` interceptor (`__asan_memcpy`), not target code.
- [x] **Real-report fixture test (human decision, 2026-11-07).** A unit test runs
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
- [x] **Fixture staleness tripwire (human decision, 2026-11-07).** An integration
      test builds `targets/bin/tlv_parser` with `targets/Makefile`, runs the
      overflow trigger through `Executor`, and asserts that the live ASan report
      parses (via the same extraction function) to the same crash site as the
      committed `tests/fixtures/` report. The fixture serves the fast unit tests;
      this integration test makes fixture drift (e.g. after AFL-010 changes
      tlv_parser) fail a test.
- [x] **Extraction fails visibly: three sentinels, never empty (human decision,
      2026-11-07; `"no_stack"` added, human decision, 2026-11-07).** The function
      never returns an empty string. It returns `"no_stack"` when stderr contains no
      ASan stack frames at all (e.g. a SIGSEGV with empty stderr; after AFL-018, also
      signals ASan may not intercept, such as SIGILL depending on `handle_sigill`),
      `"unsymbolized"` when stack frames are present but carry no function names
      (addresses only), and `"no_target_frame"` when the stack is symbolized but no
      frame comes from target source. Tests: an empty stderr returns `"no_stack"`;
      an addresses-only report returns `"unsymbolized"`; a symbolized report with
      only runtime/libc frames returns `"no_target_frame"`; none returns `""`.
- [x] **Sentinels are counted, never dropped (human decision, 2026-11-07).** A crash
      whose site is `"no_stack"`, `"unsymbolized"` or `"no_target_frame"` is still
      written as a row of `crash_events.csv` with that sentinel in `crash_site`, and
      counted in `metrics.csv`'s `crash_events`. Tests: a stubbed crash with an
      addresses-only stderr yields one `crash_events.csv` row with
      `crash_site == "unsymbolized"`; a stubbed SIGSEGV crash with empty stderr
      yields one row with `crash_site == "no_stack"`.
- [x] **Metrics output (FR-8, human, 2026-11-07).** This ticket owns and writes the
      FR-8 per-run metrics files in the format fixed in Technical notes
      ("FR-8 metrics format"), which AFL-011/012/013/014 build against.
- [x] **Hang time column (human decision, 2026-11-12; architect confirmed).**
      `metrics.csv` has a last column `hang_time_s`, after `hangs`: the running
      sum of `r.exec_time` over executions with `r.outcome == "hang"`, as fixed in
      Technical notes ("FR-8 metrics format"). It feeds no decision. Tests, with a
      stubbed executor (the fake-executor pattern of the other loop tests):
      (a) a run with `max_execs` set whose stub returns exactly K hang results,
      each with `exec_time == 1.25`, has final row `hangs == K` and
      `hang_time_s == K * 1.25`; (b) a run with no hangs has every row's
      `hang_time_s` equal to the string `0.0` as written in the file.
- [x] **Stopping (human, 2026-11-07).** The loop stops when `cfg.seconds` of
      elapsed time (measured as in AC "Clock") is spent or when `cfg.max_execs`
      executions have run (if set),
      whichever comes first. The budget is checked on every exec, and `max_execs`
      counts every target execution including S0 (AC "Exec counting"). Test: with
      a one-file seeds dir (S0 only), `max_execs = M` (M ≥ 2) and a large `seconds`,
      exactly M target executions run, i.e. the S0 execution plus exactly M − 1
      candidate executions, and the final `metrics.csv` row has `execs == M`
      (count executor `run()` calls with a stubbed or wrapped executor). The
      `max_execs = 1` boundary is tested in AC "Parameter validation".
- [x] **Clock (human decision, 2026-11-12; ADR-0005 §2).** The `cfg.seconds`
      budget and every `elapsed_s` value share one start, taken immediately before
      the first `Executor.run()` call (the S0 execution, exec 1); setup before it
      is excluded. Both the stop check and `elapsed_s` use `time.monotonic()`,
      never `time.time()`. `run.json`'s `started_at` (AFL-008) is a wall-clock
      timestamp for provenance only; nothing is measured from it. Tests: (a) with
      `time.monotonic` monkeypatched to a fake clock that only a stubbed executor
      advances (+50.0 s when the executor is constructed, +1.0 s per `run()` call),
      `seconds = 3.5` and no `max_execs`, exactly 4 executions run, the final
      `metrics.csv` row has `execs == 4`, and the row recorded after the S0
      execution has `elapsed_s == 1.0` (so the 50 s of setup is not counted);
      (b) an AST check of `src/fuzzer/fuzzer.py` finds no `time.time` attribute
      access and no `from time import time`.
- [x] **Parameter validation (human decision, 2026-11-12; ADR-0005 §2).** `run(cfg)`
      raises `ValueError` before any execution of the target, and before writing
      anything under `cfg.out_dir`, for each of: `cfg.max_execs` not `None` and
      `< 1`; `cfg.seconds <= 0`; `cfg.timeout_s <= 0`. Each message names the
      offending parameter and its value (e.g. `max_execs must be >= 1, got 0`).
      `max_execs = None` means no cap and is valid. Tests: `max_execs = 0`,
      `seconds = 0`, `seconds = -1`, `timeout_s = 0` each raise `ValueError` whose
      message names that parameter, with zero executor `run()` calls; boundary:
      `max_execs = 1` runs S0 (exec 1) and stops, with exactly one executor
      `run()` call and the final `metrics.csv` row `execs == 1`.
- [x] **Exec-index replay (human, 2026-11-07; ADR-0005).** Two runs with the same
      `cfg.seed` that stop on `max_execs` produce identical metrics streams and
      crash-event streams in every column except wall-clock fields (`elapsed_s`
      in both files, and `hang_time_s` in `metrics.csv`; human decision,
      2026-11-12). The exec index is the `execs` value defined in AC "Exec
      counting" (S0 = exec 1), so the streams match row by row from the S0
      execution onward. Timeouts are the one disclosed timing-dependent exception.
      Test: run twice on toy_parser (or a stubbed executor) with fixed seed and
      `max_execs`; compare streams with `elapsed_s` and `hang_time_s` dropped;
      both final rows have `execs == max_execs`.
- [x] **ADR-0005 written (architect).** `docs/adr/0005-*.md` records the stopping
      rule and the exec-index replay guarantee (including the timeout exception)
      before this ticket leaves review.
- [x] **NFR-2:** the schedule is chosen by one parameter, and fuzzer.py has no
      other branch on it. The two arms differ only inside schedule.py.
- [x] **NFR-1:** fuzzer.py constructs exactly one `random.Random(cfg.seed)` per
      run and passes that same object to every `mutator.mutate` call; no other RNG
      is constructed or used in the loop. Test: with a fixed exec-count/iteration
      stop (or a stubbed executor), two runs with the same `cfg.seed` produce
      identical candidate sequences, and runs with different seeds differ —
      proving the trial seed assigned by AFL-011 (`base_seed + i`) reaches the
      mutations.
- [x] **Blind mutation:** the loop never passes coverage data to the mutator.
- [x] Integration test: with UNIFORM, the fuzzer finds the toy_parser planted bug
      within a stated budget (NFR-5, M1).
- [x] **Startup guard (from AFL-002/003).** If the very first execution of the
      first seed yields zero edges, abort loudly with "no instrumentation detected"
      — the target was not built with coverage and the whole run is worthless.
      Runtime complement to the build-time tripwire in `tests/test_coverage.py`.
      Test: a target built without trace-pc-guard makes `run()` raise before any
      metrics are written.

## Technical notes (architect)
- **Interfaces (`fuzzer.py`).** cli.py (AFL-008) consumes these. run_campaign.py
  (AFL-011) reaches them through the CLI, except `seed_files`, which its pre-flight
  imports directly:
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

  def seed_files(seeds_dir: Path) -> list[Path]: ...
  def validate_config(cfg: FuzzConfig) -> None: ...
  def run(cfg: FuzzConfig) -> None: ...
  ```
- **Shared helpers (ADR-0005 §1–§2).** Like `resolve_freeze_commit` in cli.py
  (AFL-008), these are plain module-level functions, and each rule exists once.
  - `seed_files(seeds_dir)` returns the entries `p` of `seeds_dir` with
    `p.is_file()` and `not p.name.startswith(".")`, sorted by `p.name`. It may
    return `[]`; each caller decides what an empty list means. A missing dir
    raises `FileNotFoundError` from `iterdir()`.
    - Callers: `run()` loads exactly this list and raises before any execution
      if it is empty. cli.py (AFL-008) uses it for the empty-dir error and for
      the `run.json` seed list with hashes. The run_campaign.py pre-flight
      (AFL-011) requires its names to be exactly `["S0"]`.
    - No caller lists a seeds dir any other way.
  - `validate_config(cfg)` raises `ValueError` on the first failing check, in
    this order: `max_execs` not `None` and `< 1`, then `seconds <= 0`, then
    `timeout_s <= 0`. The message names the parameter and its value (e.g.
    `max_execs must be >= 1, got 0`). It has no side effects.
    - Callers: `run(cfg)` calls it first, before executor construction or any
      write under `cfg.out_dir`. cli.py calls it after building the
      `FuzzConfig` and before writing `run.json`, because AFL-008 writes
      `run.json` before `run(cfg)` starts. On `ValueError` the CLI exits
      non-zero with the message.
- **Loop.** `rng = random.Random(cfg.seed)` is created once, here. The only use of
  `cfg.schedule` in fuzzer.py is `assign_energy = schedule.SCHEDULES[cfg.schedule]`
  (per ADR-0004 §8). Then, until the budget is spent:
  `seed = corpus.select()`, `energy = assign_energy(seed, corpus)`, and for each unit
  of energy: `cand = mutator.mutate(seed.data, rng, [s.data for s in corpus.seeds])`,
  `r = executor.run(cand)`, then branch on `r.outcome` (AFL-003 three-outcome
  model): `"crash"` → record the crash event, save per the storage rule; `"hang"` → count it in `hangs` and add `r.exec_time`
  to `hang_time_s`, nothing else (never a crash, never in the corpus); `"clean"` → `corpus.observe(cand, r)`. After the energy is spent,
  `corpus.mark_fuzzed(seed)`. Check the budget on every exec, not once per seed. Close
  the executor (which unlinks the shm) in `finally`.
- Crashes and hangs never enter the corpus: only clean results go to
  `corpus.observe()`, which raises `ValueError` on any non-clean result
  (confirmed (human, 2026-11-07; ADR-0004 §2)). The mutator only ever sees bytes.
- **Stopping and reproducibility** (confirmed, human, 2026-11-07; → ADR-0005,
  architect writes it): stop at `seconds` of elapsed `time.monotonic()` time from
  just before S0 (AC "Clock") or at `max_execs`, whichever comes first. The same seed gives the same candidate sequence exec by exec. So the
  exec-indexed stream (execs, edges, corpus size, crash events) is reproducible and
  only `elapsed_s` and `hang_time_s` vary. Exact replay is guaranteed when the run stops on
  `max_execs`. Timeouts are the one timing-dependent exception. AFL-011's
  reproducibility AC is worded to match.
- **FR-8 metrics format** (owned and implemented by this ticket, human,
  2026-11-07). Fixed here so AFL-011/012/013/014 can build against it.
  - `<out>/metrics.csv`: one row on every change to edges, corpus size or crash
    events, plus a final row. Columns:
    `elapsed_s,execs,edges,corpus_size,distinct_path_ids,crash_events,crashes_saved,hangs,hang_time_s`
    (`distinct_path_ids` is required by AFL-011's pilot rule). `hang_time_s` (human
    decision, 2026-11-12) is the running sum of `r.exec_time` over executions with
    `r.outcome == "hang"` (so it includes the kill, the reap and the AFL-028 drain).
    It is a Python `float` that starts at `0.0` and is written like `elapsed_s` (the
    `csv` module's default `str(float)`, no rounding), so a run with no hangs writes
    `0.0`, never `0`. It is sampled like `hangs`: written on every row, and a hang
    does not by itself trigger a row. It is wall-clock and is excluded from replay.
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
- **Integration test:** use `targets/bin/toy_parser` (AFL-009, now in `depends_on`). Run with a fixed seed, `max_execs=1500` and a
  large `seconds`, so the test is deterministic rather than time-based. Budget reason: seed 1 first crashes at exec 688, at `scan`; the reviewer's CFG-edge model puts the median first crash over seeds 1..500 at exec 94, and seed 1 at rank 483 of 498 (a slow seed, not a lucky one), so 1500 is honest.

## Test approach (tester)
Integration test on toy_parser under a fixed seed. Review/grep check that
fuzzer.py contains no schedule-specific branch and passes no coverage to the
mutator. Unit tests with a stubbed executor for the crash save rule (cases
(a)-(c)), the `saved` link column, and each of the three crash-site sentinels.

## Review (reviewer, 2026-11-12) -- CHANGES REQUESTED (test-only)
Code is correct against every AC, ADR-0004 and ADR-0005; the invariants hold (blind
mutation: `mutator.mutate(seed.data, rng, [s.data ...])` AST-pinned; NFR-2: one
`cfg.schedule` use; NFR-1: one `random.Random(cfg.seed)`, no global `random`; the only
clock-reading branch is the stop check, `time.monotonic()` only). Gates green: ruff
clean, mypy clean (8 files), pytest 163 passed / 2 deselected, `-m slow` integration
passed. Bounced because four specified behaviours have no test that fails when they
break (mutants on a tmp copy, import path proven via `sys.modules["fuzzer.fuzzer"].__file__`):

1. **FR-8 row triggers are not pinned** (AC "Metrics output (FR-8)", AC "Hang time
   column", Technical notes "FR-8 metrics format": a row on every change to edges,
   corpus size or crash events; a hang does not by itself trigger a row). Mutant E
   (crash_events removed from the row-trigger tuple in `_Recorder.tick`) and mutant B
   (`hangs` added to it) both pass the whole suite. Fix: extend
   `test_metrics_columns_and_change_rows` (or add a sibling) with a scripted hang and a
   crash whose only state change is `crash_events`, and assert the exact list of row
   `execs` (hang exec absent, crash exec present, final row present).
2. **`distinct_path_ids` composition is not pinned** (AFL-011's pre-registered pilot
   rule reads it). Mutant D (crash `path_id`s no longer counted) passes. The chosen
   definition, clean + crash executions and never hangs, is consistent with ADR-0005
   s5 (the loop does not read a hang's edges); pin it: a crash on a path no clean exec
   took increments `distinct_path_ids`, a hang does not.
3. **AC "Initial corpus": a crashing or hanging S0 must make `observe()` raise.**
   Untested. Mutant F (S0 routed by outcome) passes: the run still dies, but in
   `select()` with `RuntimeError` after metrics.csv is written. Fix: S0 crash and S0
   hang each raise `ValueError`, with exactly one executor `run()` call.
4. **`validate_config` check order** (Technical notes "Shared helpers", ADR-0005 s2;
   cli.py reports the first message). Mutant C (first two checks swapped) passes. Fix:
   `max_execs=0, seconds=0` names `max_execs`; `seconds=0, timeout_s=0` names `seconds`.

Mutant A (clock start moved before `Executor(...)`) is killed by
`test_fake_clock_stop_and_setup_excluded`.

Checked and accepted (developer choices where the ticket was silent): first ASan stack
only + function name only (matches AFL-013 "site = function" and ADR-0005 s3, no PCs);
`crashes/` 0-based (matches `queue/id_000000`); crashing/hanging S0 raises (AC, ADR-0004
s6; test missing, item 3); mid-energy stop skips `mark_fuzzed` (ADR-0004 s3, ADR-0005
s2); `distinct_path_ids` over clean + crash (ADR-0005 s5; item 2); final row always
written (Technical notes; ADR-0005 s3 relies on it). `hang_time_s`: last column, sum
of `exec_time` over hangs, float `0.0` written as `0.0`, excluded from replay; the
no-row-trigger rule holds in code but is untested (item 1). `seed_files`, clock and
`validate_config` order are correct in code.

Integration budget (`max_execs=1500`): honest. A CFG-edge model of toy_parser driven
through the real `run()` reproduces seed 1's real first crash (exec 688, `scan`)
exactly; over seeds 1..500, 498 find a crash within 1500 execs, median first crash at
exec 94, and seed 1 ranks 483 of 498. Seed 1 is a slow seed, not a lucky one.

Non-blocking: (a) state the 1500 budget in Technical notes in place of "e.g. 200_000";
(b) the fixture note cites commit 2d55468, but the build used the staged AFL-009
Makefile (`-fno-omit-frame-pointer`); refresh it once AFL-009 is committed (the
tripwire passes); (c) `source = Path(cfg.target).name + ".c"` relies on the Makefile
`bin/%: %.c` rule, so add a comment saying so (AFL-016 naming must follow it);
(d) a stack where only runtime frames carry names (symbolizer missing) maps to
`no_target_frame`, which is right by the letter of the AC; ADR-0003 should say so;
(e) `edges` = |corpus.seen|, so crash-only edges are excluded (AFL `virgin_bits`
semantics, the same in both arms); it is the primary endpoint, so write the definition
into PRD s8 / ADR-0005 (architect); (f) AFL-011 says `distinct_path_ids` is "over all
execs"; align it with item 2 (req-engineer); (g) the link test's substring check
`'"execs": N'` also matches `N0..`; parse the JSON instead; (h) fuzzer.py line 171 (the
budget runs out between seed files) is uncovered and cannot occur in the campaign
(S0 only).

## Re-review (reviewer, 2026-11-12) -- APPROVED -> testing
All four bounce-1 items are closed. Mutants were re-run on a fresh tmp copy of `src`,
and a pytest plugin printing `sys.modules["fuzzer.fuzzer"].__file__` showed each copy
was the one imported. The unmutated control passed 38 tests. The copy was deleted
afterwards.
- B (`hangs` in the row trigger) and E (`crash_events` out of it) are killed by
  `test_row_triggers_hang_none_crash_event_yes`. It asserts rows `[1, 3, 5]`: the
  hang exec writes no row, a crash whose only change is `crash_events` writes one,
  and the final row is written. This is the FR-8 rule as the spec states it.
- D (crash `path_id` not counted), G (crash edges added to `corpus.seen`) and H
  (hang edges added to `corpus.seen`, reviewer's extra) are killed by
  `test_distinct_path_ids_counts_clean_and_crash_never_hang`. It asserts
  `distinct_path_ids == 2` and `edges == 1`, which is ADR-0005 s6: `edges` is
  `len(corpus.seen)` over clean executions only, and `distinct_path_ids` counts
  clean and crash executions, never hangs.
- F (S0 routed by outcome) is killed by both cases of
  `test_bad_s0_raises_valueerror_after_one_exec`. Each expects `ValueError` after
  exactly one exec; validation errors would show zero calls, and the mutant's
  `RuntimeError` fails the test.
- C (first two `validate_config` checks swapped) is killed by
  `test_validate_config_order_names_first_failing_parameter`, which anchors the
  message on the first failing parameter (`^max_execs must`, `^seconds must`).
- `src/` changes since bounce 1: one comment line in fuzzer.py (line 150, the
  Makefile `bin/%: %.c` naming), confirmed by a diff against the reviewed text.
  The `executor.py` diff is AFL-028's, not this ticket's.
- Non-blocking fixes are done. (a) The budget of 1500 is stated in the Technical
  notes. (b) The fixture now cites 2fc1381, and the Makefile is unchanged since then.
  (c) The comment is present. (g) The link test parses the JSON.
- Gates: ruff "All checks passed!"; mypy "Success: no issues found in 8 source
  files"; pytest "174 passed, 2 deselected"; `-m slow`: 2 passed.

## Test (tester, 2026-11-12) -- PASS
Verified in the working tree (fuzzer.py and test_fuzzer.py are uncommitted, so there is
no clean checkout of them; fuzzer.py mtime 20:42, unchanged through every run below).
Smoke and replay runs drove `fuzzer.fuzzer.run()` directly (cli.py is AFL-008), output
under a tmp dir that was deleted afterwards.
- **Gates** (after the developer's `test_crash_only_edge_enters_edges_only_after_clean_reach`
  landed): ruff "All checks passed!"; mypy "Success: no issues found in 8 source files";
  pytest "186 passed, 2 deselected" (test_fuzzer.py: 39 passed; +12 elsewhere are AFL-015's
  test_git_policy_hook.py); `-m slow`: 2 passed (before and after the new test).
- **New test, independent check:** mutant G (`corpus.seen.update(r.edges)` on the crash
  branch, tmp src copy, import path verified) fails it at `by_execs["2"] == "1"` (got
  "2"); unmutated passes.
- **Smoke, toy_parser, seed 1, max_execs 1500, both arms:** layout `metrics.csv`,
  `crash_events.csv`, `queue/id_*`, `crashes/000000.{bin,json}`; metrics header is the
  9 columns of Technical notes, `hang_time_s` last; crash_events header
  `elapsed_s,execs,signal,crash_site,path_id,saved`. Final rows (execs,edges,corpus,
  distinct,crash_events,saved,hangs,hang_time_s): uniform `1500,8,4,5,6,1,0,0.0`, fast
  `1500,7,3,4,2,1,0,0.0`. Uniform seed 1 first crash at exec 688, site `scan`, matching
  the Technical notes and toy-2 in `targets/ground_truth.json`. Hangs: 0 in every run.
- **Exec-index replay (ADR-0005 s3):** uniform seed 1 run 3 times and fast seed 1
  run 2 times (2 of these are instrumented wrappers): metrics.csv identical without `elapsed_s`
  and `hang_time_s`; crash_events.csv identical without `elapsed_s`; `queue/*` and
  `crashes/*.bin` byte-identical (sha256); `crashes/*.json` identical without
  `elapsed_s` and `stderr`. Uniform seed 2 differs in all four comparisons.
- **Arms differ only in the schedule:** the only use of `cfg.schedule` is fuzzer.py:148
  (`SCHEDULES[cfg.schedule]`). Traced energies, seed 1: both arms give S0 256 (fast:
  s=0, f=1, factor 1); at exec 257 seed 1 gets uniform 256 and fast 16. Candidate sha256
  streams are identical for execs 1..273, and first differ at exec 274, the first exec
  after fast's 16-exec energy (258..273) runs out.
- **`edges` definition (ADR-0005 s6), real runs:** per-exec outcome and edge capture.
  Uniform: final edges 8 = |clean union| 8, |clean + crash| 9, crash-only edge [13]
  excluded. Fast: 7 = 7, crash-only [13] excluded. Every row's `edges` equals
  |clean union up to that exec| in both arms.
- **Storage rule on a crash-heavy target:** tlv_parser, fast, seed 3, max_execs 300, ad hoc
  S0 `A\x05hello` (AFL-010 has no committed S0): 145 crash events, 1 saved, site `main`;
  the earliest row per site is saved; every `saved` link names an existing file whose
  JSON `execs` equals the row's.
- **Validity checklist (scope of this ticket):** explicit seed, recorded: yes;
  replay: confirmed on the real target; fixed budget honoured (`max_execs`, final
  execs == 1500); ground truth: shallow toy-2 recovered at its documented site, deep
  toy-1 not reached in 1500 execs (expected, it is the deep bug; recovering it is a
  campaign question); `hang_time_s` and `elapsed_s` excluded from replay as specified.
  The >=10 trials, MWU/A12 and dedup items are N/A here (AFL-011/012/013).
- **Non-blocking findings:** (1) fuzzer.py:103 opens the CSVs with default buffering
  and nothing flushes until `close()`: a trial killed from outside (SIGKILL, a runner
  timeout) loses its whole metrics stream, not just the tail. AFL-011 should let
  `run()` return normally, or the metrics should be line-buffered. (2) An unknown
  schedule name raises `KeyError` at fuzzer.py:148, not `ValueError`, and
  `validate_config` does not check it; AFL-008's argparse `choices` should cover it.

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
- 2026-11-12 — ADR-0005 written (architect)
- 2026-11-12 — ADR-0005 open questions resolved (architect)
- 2026-11-12 — ADR-0005 decisions turned into ACs: "Clock" (one start just before S0, `time.monotonic()` only, `started_at` provenance only; fake-clock and AST tests), "Parameter validation" (`ValueError` for `max_execs < 1`, `seconds <= 0`, `timeout_s <= 0`; `max_execs = 1` boundary), "Seed files and load order" (non-hidden regular files, `sorted()`, one shared function); "Initial corpus" and "Stopping" amended to point at them (human decision, 2026-11-12) (req-engineer)
- 2026-11-12 — Interfaces: shared `seed_files(seeds_dir)` and `validate_config(cfg)` specified in fuzzer.py, called by run(), cli.py (AFL-008) and the AFL-011 pre-flight; ADR-0005 §1 `.DS_Store` wording corrected to "untracked (gitignored once AFL-015 lands)" (architect)
- 2026-11-12 — AC "Seed files and load order": only regular files are seeds, subdirectories/non-files never read; two tests added (human decision) (developer)
- 2026-11-12 — implemented src/fuzzer/fuzzer.py + tests/test_fuzzer.py + tests/fixtures/tlv_parser_asan_memcpy.txt; all ACs ticked, tests named in the review hand-off. Integration test (slow) uses max_execs=1500 on toy_parser seed 1 (first crash at exec 688), not the 200_000 in the technical notes: this machine runs ~15 execs/s, 200k would take hours (developer)
- 2026-11-12 — `metrics.csv` gains a last column `hang_time_s` (running sum of
  `exec_time` over hang executions, drain included; float from `0.0`, written like
  `elapsed_s`; sampled with the other rows, no new row trigger). It is wall-clock,
  so the replay AC now drops `elapsed_s` and `hang_time_s`. New AC "Hang time
  column" with stubbed-executor tests (K hangs at `exec_time` 1.25 → K * 1.25; no
  hangs → `0.0`). This changes the spec after implementation, so "Hang time
  column" and "Exec-index replay" are unticked until the follow-up lands; ADR-0005
  updated to match (human decision, 2026-11-12; architect confirmed) (architect)
- 2026-11-12 — hang_time_s implemented: METRICS_COLUMNS + accumulator next to `hangs` + written in `tick()`; tests `test_hang_time_sums_exec_time` (a), `test_no_hangs_writes_literal_zero_float` (b); replay test drops `elapsed_s` and `hang_time_s`; header test asserts the literal 9-column list (developer)
- 2026-11-12 — review: changes requested (test-only), 4 numbered items in Review: FR-8 row triggers (mutants B, E survive), distinct_path_ids composition (D), crashing/hanging S0 raise (F), validate_config order (C); code, invariants and the 1500-exec integration budget accepted; moved to in-progress (reviewer)
- 2026-11-12 — review bounce 1 fixed (test-only plus notes), developer. New tests in tests/test_fuzzer.py, each proven on a throwaway src copy (import path checked via `sys.modules["fuzzer.fuzzer"].__file__`; copies deleted; unmutated code passes): B (`hangs` added to row trigger) fails `test_row_triggers_hang_none_crash_event_yes`; E (crash_events dropped from trigger) fails the same test; D (crash path_id not counted) fails `test_distinct_path_ids_counts_clean_and_crash_never_hang`; F (S0 routed by outcome) fails `test_bad_s0_raises_valueerror_after_one_exec[crash]` and `[hang]`; C (first two validate_config checks swapped) fails `test_validate_config_order_names_first_failing_parameter`. Non-blocking: (a) Technical notes now state max_execs=1500 and why; (b) fixture note cites 2fc1381; (c) Makefile-naming comment added at the `source =` line in fuzzer.py; (g) link test parses the JSON. (d)(e)(f)(h) left to other roles. Gates: ruff, mypy, pytest (and -m slow) green.
- 2026-11-12 — architect follow-up: `test_distinct_path_ids_counts_clean_and_crash_never_hang` now also asserts final `edges == "1"` (crash edge 9 and hang edges 2,3 stay out; ADR-0005 s6). Mutant G (`corpus.seen.update(r.edges)` on the crash branch, tmp copy, import path verified, deleted) fails that test; unmutated passes; ruff/mypy/pytest green (developer)
- 2026-11-12 — re-review: approved. Mutants B, C, D, E, F, G plus extra H (hang edges into `seen`) each killed on a fresh tmp copy (import path verified, copy deleted); new tests match spec and ADR-0005 s6; src delta is the one comment line; ruff/mypy/pytest (174 passed) and -m slow green; moved to testing (reviewer)
- 2026-11-12 — human decision (ADR-0005 s6, second half of the `edges` claim): added `test_crash_only_edge_enters_edges_only_after_clean_reach` in tests/test_fuzzer.py (S0 clean {1}; exec 2 crash {1,9}; exec 3 clean {1,9}; asserts edges 1 at execs 1 and 2, 2 at exec 3 and final). Tmp copy, import path verified via `sys.modules["fuzzer.fuzzer"].__file__`, copy deleted: unmutated passes; mutant G (`corpus.seen.update(r.edges)` on the crash branch) fails it; mutant I (crash edges remembered in a set, clean execs passed to `corpus.observe` with `edges - crash_edges`, so a crash-reached edge never enters `edges`) fails it. src/ unchanged (developer)
- 2026-11-12 — tester: PASS. Gates green (ruff, mypy, pytest 186 passed, -m slow 2 passed) incl. the new crash-only-edge test (mutant G killed, independently); real toy_parser smoke in both arms; exec-index replay identical on metrics/crash_events/queue/crashes (elapsed_s, hang_time_s dropped); uniform/fast candidates identical to exec 273, diverge at 274 when energy differs; final edges == clean edge union, crash-only edge excluded; 0 hangs. Two non-blocking findings (CSV buffering, KeyError on bad schedule). Left in testing for crew-lead (tester)
- 2026-11-12 — DoD verified, testing -> done (crew-lead)
  - Note: gates re-run by crew-lead at load avg ~2.5: ruff "All checks passed!", mypy
    "Success: no issues found in 8 source files", pytest "186 passed, 2 deselected". An
    earlier run during the AFL-027 stress job (load avg ~194) failed 3 ASan tests as
    `hang` (load-induced timeouts, src unchanged). Still open: "verified on a clean
    checkout" (fuzzer.py and test_fuzzer.py are uncommitted) and "commit references
    ticket ID" (the commit is the user's). Follow-up (tester's non-blocking findings, no
    code changed): (1) fuzzer.py:103 opens the CSVs with default buffering and nothing
    flushes until `close()`, so a trial killed from outside loses its whole metrics
    stream; AFL-011 should let `run()` return normally, or the CSVs should be
    line-buffered. (2) An unknown schedule name raises `KeyError` at fuzzer.py:148, not
    `ValueError`, and `validate_config` does not check it; AFL-008's argparse `choices`
    should cover it.
