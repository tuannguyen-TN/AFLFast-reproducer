---
id: AFL-007
title: Main fuzzing loop (wire everything)
requirement: FR-1..5
paper_ref: AFL whitepaper (fuzzing loop); AFLFast § power schedules (energy per seed)
module: src/fuzzer/fuzzer.py
depends_on: [AFL-002, AFL-003, AFL-004, AFL-005, AFL-006]
status: backlog
owner: developer
---

## Goal
Connect coverage (FR-1), executor (FR-2), corpus (FR-3), mutator (FR-4) and
schedule (FR-5) into one greybox loop: pick a seed, ask the schedule for its
energy, generate and run that many blind mutants, keep the ones with new
coverage. This is the M1 baseline fuzzer.

Open questions (PRD silent or ambiguous; resolve before leaving backlog):
- **FR-8 metric logging has no owner.** FR-8 lists `fuzzer.py` for logging edges,
  unique crashes and time-to-first-crash against wall-clock. AFL-014 covers only
  plots.py, and AFL-011 consumes these metrics. Either add FR-8 to this ticket's
  scope or create a separate ticket.
- The PRD does not say how seeds are selected, such as queue order or cycling.
  AFLFast also changes the search strategy, but the PRD varies only the power
  schedule. Confirm that seed selection is fixed and identical in both arms.
- How does the loop stop: wall-clock budget only, or also an execution cap?
- Reproducibility: with a wall-clock budget, the same seed may not replay the same
  run, because timing varies. AFL-011 requires replay of the metrics stream.
  Define what "reproducible" means here.
- NFR-5 needs an integration test showing the fuzzer finds the toy bug (M1). That
  needs AFL-009, which INDEX does not list as a dependency.

## Acceptance criteria
- [ ] Each iteration selects a seed from the corpus, obtains its energy from
      `assign_energy(seed, corpus)`, and generates and executes that many mutated
      candidates.
- [ ] Each candidate's coverage is checked against the global seen-set, and the
      candidate is retained iff it reveals ≥1 new edge (FR-1, FR-3).
- [ ] After a seed is fuzzed, its `times_selected` and path-frequency metadata
      are updated.
- [ ] Inputs the executor classifies as crashes are passed on for saving (FR-6,
      AFL-013).
- [ ] The loop stops when the given time budget is spent.
- [ ] **NFR-2:** the schedule is chosen by one parameter, and fuzzer.py has no
      other branch on it. The two arms differ only inside schedule.py.
- [ ] **NFR-1:** all randomness comes from one recorded seed, and the RNG passed
      to the mutator is derived from it.
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
      max_execs: int | None = None
      timeout_s: float = 1.0
      seeds_dir: Path | None = None

  def run(cfg: FuzzConfig) -> None: ...
  ```
- **Loop.** `rng = random.Random(cfg.seed)` is created once, here. The only use of
  `cfg.schedule` in fuzzer.py is `assign_energy = schedule.SCHEDULES[cfg.schedule]`
  (AFL-006 / ADR-0004 own the exact lookup form). Then, until the budget is spent:
  `seed = corpus.select()`, `energy = assign_energy(seed, corpus)`, and for each unit
  of energy: `cand = mutator.mutate(seed.data, rng, [s.data for s in corpus.seeds])`,
  `r = executor.run(cand)`, then branch on `r.outcome` (AFL-003 three-outcome
  model): `"crash"` → save the crash; `"hang"` → count it in `hangs` only (never a
  crash, never in the corpus); `"clean"` → `corpus.observe(cand, r)`. After the energy is spent,
  `corpus.mark_fuzzed(seed)`. Check the budget on every exec, not once per seed. Close
  the executor (which unlinks the shm) in `finally`.
- Crashing inputs are not added to the corpus (AFL behaviour; proposed default —
  confirm). The mutator only ever sees bytes.
- **Stopping and reproducibility** (proposed default — confirm, → ADR-0005 (to
  write)): stop at `seconds` of wall-clock or at `max_execs`, whichever comes first.
  The same seed gives the same candidate sequence exec by exec. So the exec-indexed
  stream (execs, edges, corpus size, crashes) is reproducible and only `elapsed_s`
  varies. Exact replay is guaranteed when the run stops on `max_execs`. Timeouts are
  the one timing-dependent exception. AFL-011's "reproduces its metrics stream" AC
  should be reworded to mean this (req-engineer).
- **FR-8 metrics format.** It is fixed here so AFL-011/012/013/014 can build against
  it. Whether this ticket or a new one implements it needs a req-engineer/crew-lead
  decision.
  - `<out>/metrics.csv`: one row on every change to edges or saved crashes, plus a
    final row. Columns: `elapsed_s,execs,edges,corpus_size,crashes_saved,hangs`.
  - `<out>/crashes/<n:06d>.bin` + `<n:06d>.json` holding
    `{elapsed_s, execs, signal, exit_status, path_id, stderr}`.
  - `<out>/queue/` is written by the corpus. `<out>/run.json` is written by cli.py.
- **Crash storage filter** (proposed default — confirm): save a crash only if its
  `path_id` is new among crashes. tlv_parser crashes on almost any second byte > 64,
  so saving every crash would mean tens of thousands of files per trial. The filter
  keeps the earliest input of every crash-site bucket, so dedup's unique count and
  first-crash times are unchanged. Honest unique counts come from dedup.py offline
  (AFL-013). fuzzer.py never imports `harness/`.
- **Seed selection** is fixed round-robin and identical in both arms (AFL-004).
  AFLFast also changes the search strategy (selection order), not just energy.
  Leaving that out matches PRD §8 but must be reported as a deviation: needs
  Vision/PRD decision.
- **Integration test:** use `targets/bin/toy_parser`, so INDEX should list AFL-009 as
  a dependency (req-engineer). Run with a fixed seed, `max_execs` (e.g. 200_000) and a
  large `seconds`, so the test is deterministic rather than time-based.

## Test approach (tester)
Integration test on toy_parser under a fixed seed. Review/grep check that
fuzzer.py contains no schedule-specific branch and passes no coverage to the
mutator.

## Log
- 2026-11-07 — created (req-engineer)
- 2026-11-07 — startup "no instrumentation detected" guard moved here from AFL-003
  as an AC (human decision). Loop note: branch on `r.outcome` (AFL-003 three-outcome
  model): `"crash"` → save, `"hang"` → count in `hangs` only, `"clean"` →
  `corpus.observe` (architect)
- 2026-11-07 — stale-note sweep: Technical notes "Loop" rewritten from
  `r.crashed`/`r.timed_out` to branch on `r.outcome`, matching the entry above
  (req-engineer)
