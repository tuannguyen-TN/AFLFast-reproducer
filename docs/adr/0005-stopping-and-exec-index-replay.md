# ADR-0005: Stopping rule and exec-index replay

- **Status:** accepted (human decisions, 2026-11-07, recorded in AFL-007; hang-stderr
  note per human decision, 2026-11-12, AFL-028; open questions resolved by human
  decision, 2026-11-12)
- **Date:** 2026-11-12
- **Owner:** architect
- **Related:** AFL-007, AFL-008, AFL-011, AFL-012, AFL-013, AFL-027, AFL-028, FR-2, FR-8, NFR-1,
  NFR-2, PRD §8, ADR-0002, ADR-0004

## Context
AFL-007 wires the main loop (`src/fuzzer/fuzzer.py`). Two definitions must be
written down before AFL-007 leaves review, because AFL-008 (CLI), AFL-011 (campaign
runner: its reproducibility AC and its pre-freeze timing probe) and AFL-013 (dedup)
build on them:

1. **When a run stops.** PRD §8 fixes a wall-clock budget per trial (default 600 s).
   Tests and replay checks also need a stop that does not depend on machine speed.
2. **What "reproducible" means (NFR-1).** Under a wall-clock budget, the number of
   executions a trial reaches depends on machine speed and load. So two runs with
   the same seed cannot be identical end to end. The question is what *is*
   guaranteed identical, and where timing still leaks in.

The human made these decisions on 2026-11-07. They are recorded in AFL-007: the
resolved open questions, the ACs "Exec counting", "Stopping" and "Exec-index
replay", and the technical note "Stopping and reproducibility". This ADR records
them and decides nothing new. The points that the ticket and PRD left open were
decided by the human on 2026-11-12. Each is marked "(human decision, 2026-11-12)"
where it appears below.

## Options considered
Stopping:
1. **Wall-clock only (`seconds`).** Pro: this is PRD §8's budget and Klees's
   fixed-time comparison. Con: no run replays end to end, and tests become
   time-based.
2. **Exec count only (`max_execs`).** Pro: deterministic. Con: it is not the
   PRD §8 budget.
3. **Both, whichever comes first, with `max_execs` optional.** Chosen.

Reproducibility:

a. **Full replay, timing included.** Not achievable: wall-clock fields and the
   timeout kill depend on the machine.

b. **Replay on the exec index.** Streams identical in every column except
   `elapsed_s` and `hang_time_s`, exact when the run stops on `max_execs`, with timeouts disclosed as
   the one timing-dependent exception. Chosen.

## Decision
**Stopping option 3 and reproducibility option b (human, 2026-11-07).**

### 1. The exec index
`execs` is the total number of target executions in the run. Every
`Executor.run()` call counts, whatever its outcome (`"clean"`, `"crash"`,
`"hang"`). The index is 1-based and gap-free. Initial-corpus executions come
first. The S0 execution is exec 1 (every target's seeds dir holds only S0;
ADR-0004 §6, AFL-011). The first mutated candidate is exec 2, the next exec 3,
and so on.

This one counter is:
- the `execs` column of `metrics.csv` and of `crash_events.csv`;
- the `execs` field of each `crashes/<n:06d>.json`;
- the quantity that `cfg.max_execs` limits.

**Seed load order (human decision, 2026-11-12).** The loop loads only the
regular files in `cfg.seeds_dir` whose names do not start with `.`, in `sorted()`
filename order. Python sorts `str` by code point, so the order does not depend on
the locale.
- *Why hidden files are skipped.* On macOS, Finder writes `.DS_Store` into any
  directory it opens. `.DS_Store` is untracked (gitignored once AFL-015 lands),
  so the dirty-tree check never sees it. Without this rule it would silently
  become a second initial seed.
- *Records.* `run.json` records which seed files were loaded, with their hashes
  (AFL-008).
- *Pre-flight.* AFL-011's pre-flight requires that the set of non-hidden files in
  each seeds directory is exactly {S0}. Otherwise it aborts and runs no trials.
  There is no override flag.

So the load order is fixed. In the campaign it is trivial, because the only file
loaded is S0.

### 2. Stopping rule
The loop stops when `cfg.seconds` of wall-clock has been spent, or when
`cfg.max_execs` executions have run, whichever comes first. `max_execs = None`
(the default; AFL-008 `--max-execs`) means there is no exec cap.

- **Checked on every execution**, not once per seed. A seed's energy can therefore
  be cut short. ADR-0004 §3 explains why the skipped `mark_fuzzed` call makes no
  observable difference.
- **`max_execs` counts S0.** With `max_execs = M`, exactly M executions run: S0
  plus M − 1 candidates. The final `metrics.csv` row has `execs == M`. No
  execution starts once either limit has been reached.
- **Overrun.** Because no execution starts after a limit is reached, the last
  execution can start just before the `cfg.seconds` deadline and finish after it.
  The overrun is at most one execution. For a hang, that execution lasts
  `cfg.timeout_s` plus the executor's post-kill handling (AFL-028 bounds its
  stderr drain).
- PRD §8's campaign budget is the wall-clock limit. `max_execs` is an optional
  extra cap.

**Clock start and clock source (human decision, 2026-11-12).**
- *One start.* The `cfg.seconds` budget and `elapsed_s` share one start. It is
  taken immediately before the first `Executor.run()` call, the S0 execution
  (exec 1).
- *Setup is excluded.* Setup is identical in both arms, and leaving it out keeps
  setup noise out of time-to-first-crash.
- *Monotonic clock.* Both the stop check and `elapsed_s` use `time.monotonic()`,
  never `time.time()`. Wall-clock time can jump (NTP adjustments, sleep and
  wake), and a jump would distort `elapsed_s` and the stop check.
- *`started_at`.* `run.json`'s `started_at` (AFL-008) stays a wall-clock
  timestamp. It is for provenance only, and nothing is measured from it.

**Parameter validation (human decision, 2026-11-12).** `run(cfg)` in
`src/fuzzer/fuzzer.py` raises a clear `ValueError` for each of these, with one
message per parameter:
- `cfg.max_execs < 1`;
- `cfg.seconds <= 0`;
- `cfg.timeout_s <= 0`.

Validating in `run()` covers every caller (cli.py, run_campaign.py via the CLI,
tests). `max_execs = None` means no cap, as above. `max_execs = 1` runs S0
(exec 1) and stops. That boundary is tested.

### 3. Exec-index replay guarantee
**Statement.** Take two runs with the same `cfg.seed`. Their exec-indexed streams
are the same: `metrics.csv` and `crash_events.csv` are identical row by row, in
every column except `elapsed_s` and `metrics.csv`'s `hang_time_s`, from the S0
execution (exec 1) onward. This is subject to the timeout exception (§4).

- **Exact replay on `max_execs`.** When both runs stop on `max_execs`, both files
  are identical in full once `elapsed_s` and `hang_time_s` are dropped. Both final rows have
  `execs == max_execs`.
- **Wall-clock stop.** A run stopped by `cfg.seconds` reaches an exec index that
  depends on the machine. Replay is guaranteed only up to the exec index it
  reached, and nothing is guaranteed beyond it (AFL-011 uses the same wording).
  To compare two such runs, compare the rows up to the smaller of the two final
  exec indexes. Leave out the final row of the run that stopped first: it marks
  where that run stopped, not a change of state.

**Inputs that must match.** Besides `cfg.seed`: `cfg.schedule`, `cfg.timeout_s`
and `cfg.max_execs`; the same target binary; the same S0 bytes; and the same
platform and toolchain, because symbolization feeds `crash_site`. AFL-011 records
the commit, the config and the S0 hash, and that is how a re-run shows these
inputs match.

**Why it holds.** AFL-007 must preserve each link of this chain:
- **One RNG.** `random.Random(cfg.seed)` is constructed once in `run()`. It is
  the only RNG, and only `mutator.mutate` draws from it (AFL-007 NFR-1 AC).
- **Every other decision is a deterministic function of earlier outcomes.**
  - Selection is round-robin with no RNG (ADR-0004 §4).
  - Energy is a pure function of `times_selected`, `path_freq` and
    `len(corpus.seeds)` (ADR-0004 §8 and its amendment).
  - Retention and f(i) are functions of the clean edge sets (ADR-0004 §2).
  - The splice pool is the seeds' bytes in insertion order.
  - The crash storage rule only tests membership in its two sets. It never
    depends on set iteration order.
- **Each outcome is a function of the input bytes.** An execution's outcome, its
  edge set and its crash stderr depend only on the input bytes, given the same
  binary. The targets read only stdin (plus `FUZZ_SHM_NAME` in `cov_rt.c`), and
  use no clock and no randomness. The executor fixes `ASAN_OPTIONS` (ADR-0002).
  The one exception is the timeout (§4).
- **No wall-clock quantity feeds a decision.** Wall-clock appears in only three
  places:
  - the `elapsed_s` fields (`time.monotonic()`, §2);
  - the stop check (`time.monotonic()`, §2);
  - `ExecResult.exec_time`, which is copied to `Seed.exec_time`. No schedule reads
    it (ADR-0004 amendment). The only stream column that carries it is
    `hang_time_s`, its sum over hang executions, which feeds no decision.

**Scope.** The guarantee covers the two streams the AC names: `metrics.csv` and
`crash_events.csv`. Files written from the same exec-indexed decisions follow from
it: `queue/id_*`, `crashes/*.bin`, and the `saved` paths that name those files.
Outside the guarantee:
- `elapsed_s`, wherever it appears;
- `hang_time_s` in `metrics.csv` (human decision, 2026-11-12): the running sum of
  `ExecResult.exec_time` over executions with outcome `"hang"`, so it includes the
  kill, the reap and the AFL-028 drain; AFL-011's timing probe reads it;
- the `stderr` field of `crashes/*.json`. ASan reports carry the PID and absolute
  addresses, and these differ from process to process;
- `run.json` (AFL-008).

**`crash_site` is replay-safe (binding; human decision, 2026-11-07, AFL-013;
confirmed 2026-11-12).** `crash_site` is a column of the replayed
`crash_events.csv`. The human fixed its format in AFL-013's open questions. It is
the value returned by AFL-007's shared extraction function in `src/fuzzer/`: the
first in-target frame of the symbolized ASan report.
- There is no top-N frame hash.
- There is no absolute PC.
- The signal is not part of it.

So `crash_site` contains no absolute addresses and no PIDs, and identical crashes
in different processes give the same string. AFL-013 / ADR-0003 must keep the
format free of process-varying content, or this guarantee breaks.

**A missing symbolizer gives `no_target_frame` (added 2026-11-12, AFL-007
review).** ADR-0003 is not written yet. AFL-013 writes it and must carry this
paragraph over.
- `crash_site()` returns `"unsymbolized"` only when no frame of the first stack
  has a function name. When some frames have names but none is in the target's
  source file, it returns `"no_target_frame"`.
- Without a working symbolizer, the ASan runtime and system-library frames can
  still have names (from their exported symbols), but the target's frames have no
  `file:line`. That report is labelled `"no_target_frame"`, not `"unsymbolized"`.
  A target built without `-g` gets the same label: `-g` is in the Makefile's
  overridable `CFLAGS`, not in `REQUIRED_FLAGS`.
- This is right by the letter of the AFL-007 AC (test `test_crash_site_variants`,
  the runtime-frames-only case). But it means `"no_target_frame"` does not tell
  "symbolization failed" apart from "crashed outside the target". Whether to add a
  check for this is open (see Open questions).

### 4. The timeout exception
Timeouts are the one disclosed timing-dependent exception.

**Why timing leaks in.** An execution is a hang when it does not finish within
`cfg.timeout_s` of wall-clock. That depends on machine load as well as on the
input. So an input whose run takes close to the timeout can be a hang in one run
and not in the other. The executor ranks hang above crash, so a slow crashing
input can also become a hang.

**How far a difference reaches.** One differing classification changes that
execution's effect on the streams: the `hangs` count, and the crash event or the
corpus update the execution would otherwise have caused. Through the corpus, the
difference then spreads to everything after it. If a clean input is retained in
one run but counted as a hang in the other, the corpus differs from then on, and
so do f(i), the splice pool and the seed order. The same RNG draws then produce
different candidates. This happens in both arms, UNIFORM included. So the
guarantee holds up to the first execution whose hang/non-hang classification
differs between the two runs. After that execution, the streams may diverge for
the rest of the run.

**Parallel trials make it worse.** Running trials in parallel adds machine load.
That makes a timeout-boundary input more likely to be classified differently
between two runs.

**Monitoring (decided elsewhere).** AFL-011's pre-freeze timing probe measures
toy_parser's hang rate on an otherwise idle machine. The expected rate is 0. A
nonzero rate is a reason to raise `--timeout` before the freeze (human,
2026-11-12). This hang rate is how the exception is monitored. The AFL-007 replay
test runs on toy_parser or on a stubbed executor. The exception applies in the
same way to both arms (NFR-2).

**PRD cross-reference (human decision, 2026-11-12).** PRD §8's threats to
validity gets a one-line entry that points at this section (req-engineer writes
it). The entry says three things:
- whether a run hangs depends on machine load, and parallel trials make that
  worse;
- one differing hang changes the later corpus, so replay holds only up to the
  first differing timeout;
- the timing probe's hang rate on toy_parser (expected 0) is the monitor.

### 5. Hang stderr is not an input to any metric or to replay
The loop reads a hang result only through `r.outcome == "hang"`, and then only
increments `hangs` and adds `r.exec_time` to `hang_time_s`. It does not read a hang's `stderr`, or its `edges`, which are
empty. A hang never reaches `corpus.observe()`, is never a crash event, and is
never saved. So no column of `metrics.csv` or `crash_events.csv`, and no saved
file, derives from hang stderr. The crash-site extractor runs on crash results
only.

This is consistent with AFL-028 (human decision, 2026-11-12). AFL-028 changes the
executor's hang path so that a timed-out run's stderr is fully drained after the
kill, within a short bound. It does not change the executor interface. Of the
`ExecResult` fields, it changes only how complete a hang's stderr is. AFL-007
does not depend on it. Its only effect on a run is the time the drain takes. That
time can change `elapsed_s`, `hang_time_s` and how many executions fit into
`cfg.seconds`. It
never changes an exec-indexed value. Making any metric, or the replay comparison,
depend on hang stderr would need an amendment to this ADR.

### 6. What `edges` and `distinct_path_ids` count (added 2026-11-12, AFL-007 review)
`edges` feeds a pre-registered primary endpoint: AFL-012's `final_edges` is the
`edges` value in the final row of `metrics.csv` (PRD §8). This section states what
that column counts, and what `distinct_path_ids` counts. It describes the code in
`src/fuzzer/fuzzer.py` and `src/fuzzer/corpus.py` as reviewed for AFL-007. It
decides nothing new.

**`edges`** is `len(corpus.seen)`: the number of distinct edge ids hit by at least
one execution with outcome `"clean"`, from S0 (exec 1) up to that row's exec index.
- *Clean executions count.* Only `corpus.observe()` adds to `corpus.seen`, and it
  accepts clean results only. It adds a result's edges when at least one of them
  is new; otherwise all of them are in `seen` already. So `seen` is the union of
  the edge sets of every clean execution so far. "Clean" is the executor's
  outcome (AFL-003, ADR-0002): not timed out, and not killed by SIGSEGV or
  SIGABRT. A nonzero exit status is clean.
- *Crashes do not count.* The loop uses a crash's edges only for its `path_id`
  (`distinct_path_ids` and `crash_events.csv`). An edge reached only by crashing
  inputs is not in `edges`. It enters `edges` only if a clean execution later
  reaches it. So finding a bug does not by itself raise `edges`; bug finding is
  measured by time-to-first-crash.
- *Hangs do not count.* A hang's edge set is empty (the executor drops the
  bitmap on a timeout), and the loop does not read it (§5).
- *Why.* This is AFL's rule. In afl-fuzz's `save_if_interesting()`, a normal
  execution is checked against `virgin_bits`, a timeout against `virgin_tmout`
  and a crash against `virgin_crash`. AFL's reported coverage (`bitmap_cvg` in
  `fuzzer_stats`) is counted from `virgin_bits` only, and AFLFast inherits this.
  It is also the set that retention already keeps, so no second coverage set is
  needed. The rule is the same in both arms (NFR-2).
- *Remaining difference from AFL.* AFL's map holds hashed (previous, current)
  location pairs with hit-count buckets. `edges` counts trace-pc-guard ids,
  presence only (ADR-0001).
- *Rows.* Every change to `edges` writes a row, so edges over time (AFL-012's
  `edges_auc`) is exact at every change.

**`distinct_path_ids`** is the number of distinct `coverage.path_id(r.edges)`
values over every clean and every crash execution so far, S0 included. Hangs
never count (§5). It differs from `edges` in two ways: it includes crashing
executions, and it counts distinct edge sets, not edges. An edge set seen in both
a clean and a crashing execution counts once. AFL-011's pilot rule reads it.
- *Rows.* A change to `distinct_path_ids` alone does not write a row. Rows are
  written when `edges`, `corpus_size` or `crash_events` changes, plus the final
  row. Each row holds the exact value at its exec index, and the final row holds
  the run's final value.

## Consequences
- **Tests (AFL-007).**
  - Exec counting: with S0 only, the first candidate is `execs == 2`.
  - Stopping: count `run()` calls; with `max_execs = M` there are S0 plus M − 1
    candidates, and the final row has `execs == M`.
  - Replay: run twice with a fixed seed and `max_execs`, drop `elapsed_s` and
    `hang_time_s`, and check that both final rows have `execs == max_execs`.
  - Boundary: `max_execs = 1` runs S0 only and stops.
  - Validation: `max_execs < 1`, `seconds <= 0` and `timeout_s <= 0` each
    raise `ValueError` with that parameter's message.
  - Seed loading: a hidden file (e.g. `.DS_Store`) in the seeds dir is not
    loaded.
  - Use toy_parser or a stubbed executor, so that no test depends on a hang
    classification.
- **Implementation constraints on fuzzer.py.**
  - The stop check is the only branch that reads the clock.
  - No second RNG.
  - No decision depends on set or dict iteration order.
  - Nothing reads hang stderr (§5).
- **Main-campaign trials stop on the wall-clock limit (PRD §8).** Their
  end-of-budget values reproduce only as functions of the exec index. This
  applies to final edges (a primary endpoint), to the final `execs`, and to each
  first crash at a site. The exec index of each first crash replays, but its
  `elapsed_s` does not. A re-run on a faster or busier machine reaches a
  different exec index within the same `seconds`. AFL-011's reproducibility AC is
  worded at this level.
- **NFR-2.** Both arms share the stopping rule, the exec counter and the timeout.
  Under a wall-clock stop, the arms can reach different exec counts, because they
  execute different inputs. That is inherent to a fixed-time budget (PRD §8,
  Klees). It is not a second independent variable.
- **AFL-028 is independent of AFL-007** (§5). It can land before or after
  AFL-007.
- **Disclosure.** The timeout exception goes into the report as the one
  timing-dependent limit on replay, and into PRD §8's threats to validity
  through the one-line entry that points at §4.

## Open questions for the human
One, added 2026-11-12 from the AFL-007 review (below). The human resolved the
first five on 2026-11-12:
- clock start and source: §2;
- seed load order: §1;
- `crash_site` format: §3, binding per AFL-013;
- parameter validation: §2;
- PRD cross-reference: §4.

**Symbolizer check (added 2026-11-12, AFL-007 review).** Is the
`"no_target_frame"` label for a failed symbolization (§3) acceptable as it is, or
should AFL-011 check before a run that symbolization works?
- *What is at stake.* The failure is silent and the same in both arms, so it
  favours neither. But every crash would land in one unknown bucket, every
  per-bug time-to-first-crash would be censored, and the deep-bug primary
  endpoints would be all ties. AFL-012's sentinel flag shows this only after the
  campaign has run.
- *What already covers it.* AFL-011 checklist item (b), `pytest -m slow`, asserts
  real crash sites for toy_parser (depth sweeps) and tlv_parser (the AFL-007
  fixture tripwire). That runs once, on the freeze commit, under pytest's
  environment, not the trials'.
- *Recommendation (architect; not decided).* Add a pre-run check to AFL-011.
  Before each pilot, confirmation pilot and main campaign, in the environment the
  trials run in and on the rebuilt binaries, run one known trigger per planted bug
  through `Executor` and require `crash_site()` to return that bug's `function`
  from `targets/ground_truth.json`. Abort if any does not. This is better than
  checking that `llvm-symbolizer` is on `PATH`: it also catches a target built
  without `-g` and a symbolizer that is found but fails, and it costs a few
  executions. `ground_truth.json` has no trigger field today; the triggers are in
  the target tests.
