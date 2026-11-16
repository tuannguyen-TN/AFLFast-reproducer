# Product Requirements Document — greybox-fuzz-repro

| | |
|---|---|
| **Project** | Naive coverage-guided greybox fuzzer; reproduction of AFLFast under Klees evaluation |
| **Course** | Computer Security |
| **Due** | 2026-11-22 |
| **Status** | Draft v1.0 |
| **Source of truth** | This document. Code deviating from it requires a ticket to change one or the other. |

---

## 1. Problem statement

A prior report defined a fuzzer only at a surface level. This project corrects
that by **building** a working coverage-guided greybox fuzzer and using it to
**reproduce a published result** with **publishable-grade evaluation**. The
value is not a novel tool — it is demonstrated understanding of *how greybox
fuzzing works* and *how fuzzing claims must be measured to be trustworthy*.

## 2. Goals

- **G1.** Implement a working AFL-style coverage-guided greybox fuzzer in Python
  driving instrumented C targets.
- **G2.** Implement two power schedules behind one toggle: `UNIFORM` (baseline,
  vanilla-AFL behaviour) and `FAST` (AFLFast exponential schedule).
- **G3.** Reproduce the **direction** of AFLFast's result: `FAST` reaches more
  coverage and/or more unique crashes and/or faster time-to-first-crash than
  `UNIFORM`, at small scale.
- **G4.** Evaluate per Klees et al.: multiple trials, statistical significance,
  effect size, and honest crash de-duplication.
- **G5.** Produce a short report whose evaluation section is rigorous enough to
  answer the "too shallow" critique.

## 3. Non-goals

- **NG1.** Competing with real AFL/AFLFast on absolute performance or real CVEs.
- **NG2.** Reproducing AFLFast's absolute numbers (24h campaigns, binutils, CVE
  counts). We reproduce the *direction* at reduced scale and say so explicitly.
- **NG3.** Fuzzing any software we do not own, or anything over a network.
- **NG4.** Novel fuzzing research contributions.
- **NG5.** Source-less / binary-only instrumentation (noted as future work).

## 4. Background (what each paper contributes)

- **AFLFast (CCS 2016)** supplies the *claim under test*. It models greybox
  fuzzing as a Markov chain and shows most tests re-walk a few high-frequency
  paths; allocating **energy** via a **power schedule** toward low-frequency
  (rare) paths finds bugs faster. This project implements that schedule.
- **Klees et al. (CCS 2018)** supplies the *measurement standard*. Fuzzing is
  random, so single-run comparisons are untrustworthy; claims need many trials,
  significance testing (Mann-Whitney U), effect size, defined time budgets,
  and crash-dedup that does not overcount bugs. This project obeys those rules.

## 5. Success criteria (acceptance at project level)

- **SC1.** `make -C targets` builds instrumented targets and the fuzzer runs end
  to end. For every experiment target, each documented planted bug's trigger
  crashes at its site through the executor, and the fuzzer discovers each
  **shallow** planted bug in ≥1 main-campaign trial. A **deep** planted bug that
  no main-campaign trial finds is a reportable null for that bug
  (time-to-first-crash censored at the per-trial budget), not an SC1 failure.
  *(Changed 2026-11-07, human decision: with deep bugs in every target, "every
  bug found" could fail SC1 on a valid experimental result.)*
- **SC2.** `--schedule {uniform,fast}` selects the schedule; difference is
  isolated to `schedule.py` (no other behavioural change between arms).
- **SC3.** `run_campaign.py` executes ≥10 trials per (target × schedule) with
  distinct, recorded RNG seeds and a fixed per-trial time budget.
- **SC4.** `aggregate.py` reports, per metric: median + IQR, two-sided
  Mann-Whitney U p-value, and Vargha-Delaney A12 effect size. For each member of
  the primary family (§8) it also reports the Holm-Bonferroni-adjusted p-value, and
  it labels every other comparison exploratory. *(Changed 2026-11-12, human
  decision: two-sided test; primary family with Holm-Bonferroni; exploratory
  labelling.)*
- **SC5.** `plots.py` emits coverage-over-time and unique-crashes-over-time
  figures with median lines and inter-trial variance bands.
- **SC6.** The report states the hypothesis, the result (direction + whether
  significant), and the scale limitation, with no overclaiming.

## 6. Functional requirements

| ID | Requirement | Acceptance criteria | Module |
|---|---|---|---|
| **FR-1** | Collect edge coverage from an instrumented target | Given a target built with `-fsanitize-coverage=trace-pc-guard`, after a run the fuzzer obtains the hit edges, each with its AFL hit-count bucket (the set of (edge, bucket) pairs), and can tell if any pair is new vs. the global seen-set *(Changed 2026-11-16, AFL-036, to match the ADR-0001 amendment of 2026-11-15 (AFL hit-count buckets): was "obtains the set of hit edges and can tell if any are new vs. the global seen-set".)* | `coverage.py` |
| **FR-2** | Execute a target on one input safely | Runs target on stdin/file input, enforces a timeout, returns (exit status, terminating signal, coverage); a run ended by any terminating signal is a crash, except a run killed by the executor's own timeout, which is a hang; a non-zero exit with no signal is clean (precedence hang > crash > clean) *(AFL-018, human decision 2026-11-07)* | `executor.py` |
| **FR-3** | Manage the seed corpus | A candidate is retained **iff** it reveals ≥1 new (edge, bucket) pair; each seed stores metadata (times_selected, exec_time, size, path-frequency); corpus persists to disk *(Changed 2026-11-16, AFL-036, to match the ADR-0001 amendment of 2026-11-15 (AFL hit-count buckets): was "A candidate is retained **iff** it reveals ≥1 new edge".)* | `corpus.py` |
| **FR-4** | Mutate inputs (blind) | Implements bit/byte flips, arithmetic inc/dec, interesting-value injection, havoc (stacked), and splice; mutation never reads coverage | `mutator.py` |
| **FR-5** | Power schedules | `SCHEDULES[name](seed, corpus)`, name ∈ {`uniform`, `fast`} (ADR-0004 §8), returns an int ≥ 1; `UNIFORM` returns a constant (256); `FAST`, with s = s(i) and f = f(i): for s < 16, energy = 256·min(⌊2^s/f⌋, 16), a ramp in s capped at 4096; for s ≥ 16, energy = 256·min(⌊32/next_p2(f)⌋, 16), independent of s (AFLFast afl-fuzz.c:4803-4806), so energy drops at s 15→16 for 3 ≤ f ≤ 32768; a zero factor gives 16 while the corpus holds ≤ 10 seeds, else 1. At equal s, a seed with lower f never gets less energy | `schedule.py` |
| **FR-6** | Detect & de-duplicate crashes | Crashing inputs saved with signal + faulting context; dedup buckets by crash site, the function of the first in-target stack frame (no PC, no top-of-stack hash; ADR-0003); dedup heuristic documented *(Reworded 2026-11-15 to match ADR-0003, a clarification made before any data depended on it; lead decision, 2026-11-15.)* | `executor.py`, `dedup.py` |
| **FR-7** | Run campaigns | From a YAML config, run N trials × targets × schedules; trial i uses `base_seed + i`; writes per-trial time-series metrics | `run_campaign.py` |
| **FR-8** | Record & plot metrics over time | Logs edges, unique crashes, and time-to-first-crash vs. wall-clock; plots with variance bands | `fuzzer.py`, `plots.py` |
| **FR-9** | Statistical analysis | Median + IQR; two-sided Mann-Whitney U (report U, p); A12 effect size; Holm-Bonferroni-adjusted p across the §8 primary family; each comparison labelled primary or exploratory; comparison table UNIFORM vs FAST *(Changed 2026-11-12, human decision.)* | `aggregate.py` |
| **FR-10** | CLI | Single-run CLI exposing target, schedule, time budget, seed, output dir | `cli.py` |

## 7. Non-functional requirements

- **NFR-1 Reproducibility.** Every randomised decision derives from a recorded
  seed; dependencies pinned; each result records commit hash + exact command.
- **NFR-2 Isolation of the variable.** The only difference between experimental
  arms is the power schedule. Enforced by review (see `.claude/agents/reviewer.md`).
- **NFR-3 Performance.** Target ≥500 execs/sec on the toy targets on a laptop;
  if far below, document the executor bottleneck (does not block the result).
- **NFR-4 Portability.** Linux + clang; documented in README; no exotic deps.
- **NFR-5 Code quality.** `ruff` clean, `mypy` clean on `src/`, unit tests for
  `mutator.py` and `schedule.py`, ≥1 integration test (fuzzer finds toy bug).
- **NFR-6 Scope/ethics.** Local-only, own-targets-only; no network calls anywhere.

## 8. Experimental design (the Klees layer — this is what earns the grade)

- **Independent variable:** power schedule ∈ {UNIFORM, FAST}.
- **Dependent variables:** (a) edges covered over time, (b) # unique crashes
  (deduped), (c) time-to-first-crash per planted bug. Endpoints are evaluated at the end of the budget; an execution that finishes after the deadline (the at-most-one-execution overrun, ADR-0005 §2) contributes to no endpoint. *(Added 2026-11-15, lead decision, 2026-11-15.)*
- **Targets:** ≥3 (toy_parser, tlv_parser, + one more, e.g. a mini format parser).
  Each experiment target carries **≥2 planted bugs**, each at a distinct crash
  site in a distinct function (so crash-site dedup maps them to distinct
  buckets), of differing depth relative to the target's shipped seed S0: ≥1
  **shallow** (some single-byte substitution of S0 crashes at its site, so either
  arm should reach it early) and ≥1 **deep** (no single-byte substitution of S0
  crashes at its site; reached only via a documented chain of ≥3 inputs, each
  adding new coverage). Measurement procedure in the target tickets. Each bug is
  recorded as ground truth. S0 is committed at `targets/seeds/<target>/S0` and is
  each trial's sole initial corpus in both arms, so bug depths are measured against
  the input the fuzzer actually starts from. *(Changed 2026-11-07, human decision: with one bug per
  target, (b) could only be 0 or 1 per trial.)*
- **Trials:** ≥10 independent trials per (target × schedule), distinct seeds.
- **Budget:** fixed wall-clock per trial (default 600s; scaled down from
  AFLFast's 24h — a deliberate, stated limitation, not a flaw).
- **Analysis:** per metric, median + IQR; plots with variance bands. Each UNIFORM
  vs FAST comparison uses a **two-sided** Mann-Whitney U test at α=0.05 and the
  Vargha-Delaney effect size A12(FAST, UNIFORM), which gives the direction and the
  size of the difference: A12 > 0.5 means FAST's values tend to be larger. The
  **primary family** is fixed before any pilot data exists. It holds, per target,
  the final edges covered at the end of the budget and, per **deep** planted bug
  (as defined above), the time-to-first-crash. A trial that does not find a bug
  gives a time-to-first-crash right-censored at the per-trial budget: it is never
  dropped and never clamped to the budget, and in the test all censored trials are
  ranked as tied with each other and above every observed time. Holm-Bonferroni
  corrects across the primary family, and a primary comparison is significant only
  when its Holm-adjusted p < 0.05. Every other comparison is **exploratory**: it is
  reported with its uncorrected p-value and labelled exploratory wherever it
  appears. The exploratory comparisons include unique crashes (deduped), the
  time-to-first-crash of each shallow bug, and the area under the
  coverage-over-time curve, a secondary coverage measure; final edges is the
  primary one. *(Changed 2026-11-12, human decision: two-sided test with A12 for
  direction and effect size; a pre-specified primary family corrected by
  Holm-Bonferroni, with all other comparisons exploratory and uncorrected; final
  edges as the primary coverage measure and the coverage-curve area as a
  secondary, exploratory one. Previously one uncorrected test per metric, with no
  stated sidedness or coverage scalar.)*
- **Crash dedup:** by crash site; the heuristic is named and its known
  overcounting bias acknowledged (per Klees). The unique-crash count (dependent variable (b)) is the number of distinct real crash sites, i.e. dedup buckets whose site is a target function, counting only crash events within the budget; the three catch-all buckets (`no_stack`, `unsymbolized`, `no_target_frame`) are excluded from it and their crash events are reported separately as per-trial sentinel counts, because they cannot be matched to a planted bug and include crashes the target did not raise (e.g. an OS kill) (ADR-0003). *(Added 2026-11-15, lead decision, 2026-11-15: the measure is exploratory and no pilot or campaign data existed when it was decided.)*
- **Hypothesis (H1):** on at least one member of the primary family, FAST differs
  from UNIFORM at Holm-adjusted p < 0.05 (two-sided) in FAST's favour as A12
  shows it: A12 > 0.5 for final edges (more coverage), or A12 < 0.5 for a deep
  bug's time-to-first-crash (found earlier). H1 is not supported when no primary
  member reaches Holm-adjusted p < 0.05. A primary member that is significant in
  UNIFORM's favour is reported as a significant result against H1 on that
  endpoint. If primary members are significant in both directions, the result is
  reported as mixed, with each endpoint's direction stated; H1 is not described
  as supported overall. Exploratory comparisons neither support nor refute H1. A
  null result, reported with these statistics, is a passing outcome (§11);
  overclaiming is a failing one. *(Changed 2026-11-12, human decision: was "FAST
  ≥ UNIFORM on coverage and unique crashes, and ≤ on time-to-first-crash, with
  p < 0.05 on at least one metric/target"; the mixed-result rule for primary
  members significant in both directions was added at the same time.)*
- **Threats to validity:** small targets, short budgets, single machine; all
  disclosed in the report. Also a deliberate deviation: AFLFast as published
  combines a power schedule with a search strategy that prioritises seeds with
  low s(i) (chosen less often) and low f(i) (exercising low-frequency paths). This
  reproduction isolates the power schedule: both arms select seeds by the same
  fixed round-robin, and AFL's favored-seed culling and skip probabilities are
  omitted in both. Results therefore bear on the power schedule alone, not on
  AFLFast as a whole, and UNIFORM is not identical to vanilla AFL's queue
  behaviour (ADR-0004). The paper's own Fig. 11 shows the schedule-only ('No
  Strategy') configuration yields a smaller gain than full AFLFast, so a reduced
  effect size in this reproduction is consistent with the source, not necessarily
  a harness artifact. A second deliberate deviation concerns AFL's deterministic
  stage: AFLFast (Böhme et al., CCS 2016, §4.3) notes that AFL runs it the first
  time a seed is fuzzed and, because its power schedules assign far less energy
  initially, defers it until the assigned energy reaches what deterministic
  fuzzing would cost; this reproduction drops it in both arms (AFL-005), so energy
  is the only per-seed budget and the walk's operators run only as havoc steps.
  Further deviations lie in the energy computation itself (AFL-006, ADR-0004),
  checked against AFLFast's source code, which is based on AFL 2.51b. (i) f(i)
  counts clean executions only, whereas AFLFast's `n_fuzz` (afl-fuzz.c:3144) also
  counts crashing and hanging executions. (ii) AFL's per-seed α(i) adjustments
  (execution speed, bitmap size, handicap, depth) are dropped in both arms; α is
  the constant 256, AFL's `HAVOC_CYCLES` at the base `perf_score` of 100.
  (iii) UNIFORM is equivalent to AFLFast's EXPLORE schedule (factor 1), not to its
  EXPLOIT ("AFL") schedule, which sets the factor to `MAX_FACTOR` and so
  saturates at 4096 executions per seed. (iv) A FAST seed whose factor rounds to
  zero receives `HAVOC_MIN` (16) executions in AFLFast while `queued_paths` ≤ 10
  and is skipped above 10 (afl-fuzz.c:5160, :6170; the fix from aflfast issue
  #5). We match the ≤ 10 regime and give such a seed 1 execution instead of
  skipping it above 10. Coverage uses AFL's hit-count buckets (1, 2, 3, 4-7,
  8-15, 16-31, 32-127, 128+): corpus retention, `path_id` and hence f(i) are
  computed over (edge, bucket) pairs, identically in both arms (AFL-034; ADR-0001
  amendment of 2026-11-15). Each guard's 8-bit hit counter saturates at 255,
  whereas AFL 2.x, on which AFLFast builds, wraps it. The primary coverage measure
  is unchanged: final edges is the number of distinct edge ids hit by clean
  executions, not a count of (edge, bucket) pairs. Path ids and corpus sizes from
  before the switch (the first pilot) are not comparable with later ones.
  *(Changed 2026-11-16, AFL-036, following the ADR-0001 amendment of 2026-11-15
  (lead decision, 2026-11-15), made when the pre-registered granularity rule
  (AFL-011) fired on the first pilot: was "From the same inputs, presence-only
  retention keeps a subset of what AFL's hit-count bucketing keeps, so our corpus
  tends to reach 10 seeds later than AFL's queue would.")* (v) β = 1,
  following AFLFast's code (`POWER_BETA`, config.h:92); the paper's text says
  β > 1. (vi) AFL's doubling of the havoc budget when a new path is found
  (afl-fuzz.c:6576-6578) is omitted in both arms, so 4096 is a hard per-seed
  energy cap here, whereas AFL and AFLFast can exceed it. (vii) `havoc_div`
  (afl-fuzz.c:4399-4401), which shrinks the havoc budget for slow targets, is
  dropped in both arms. Our measured throughput at the campaign concurrency `c` = 3
  is about 14.1 executions per second on toy_parser, 13.2 on tlv_parser and 13.6
  on mini_format (rounded to one decimal; per target, the lower of its two
  schedules' counted trials over both official runs of the AFL-011 timing probe,
  here all from official run 2, on the candidate freeze commit 1aa932f). This
  throughput comes from executor overhead (a new process per run plus ASan start-up), not from the
  targets themselves. These parsers do almost no work per input, so under AFL's
  fork server they would almost certainly fall in the fast band, where
  `havoc_div` = 1. Their speed under a fork server was not measured. If the campaign runs at `c` = 3 trials at once (the one revision from `c` = 5 that AFL-011 item (d) permits), including when `c` = 3 is itself below 80 % of the concurrency-1 baseline's per-trial exec/s, the lower per-trial exec budget is reported as a threat to validity. *(Added 2026-11-15, lead decision, 2026-11-14.)* The campaign runs at `c` = 3. At `c` = 5 every target was below 80 % of the concurrency-1 baseline (lower per-trial exec/s of the two arms: toy_parser 51.7 %, tlv_parser 56.8 %, mini_format 74.0 %), so item (d) revised `c` to 3. At `c` = 3 toy_parser was still below 80 % (77.5 %; tlv_parser 98.4 %, mini_format 108.3 %), so `c` stays 3. *(Added 2026-11-15, lead decision, 2026-11-15.)* (viii) For s(i) ≥ 16, FAST's factor becomes 32 / next_p2(f(i)), independent of s(i) (AFLFast afl-fuzz.c:4803-4806), so energy drops at s(i) 15→16 for every 3 ≤ f(i) ≤ 32768 (f = 5: 4096 → 1024; f = 33: 4096 → 16 or 1). We follow AFLFast's code here, so this is not a deviation from AFLFast; it is a deviation from the paper's eq. 4 as written, whose factor 2^s(i)/f(i) has no such branch.
  Timing-dependent hangs: whether an execution hangs depends on machine load as well as on the input, and parallel trials make this worse; one differing hang changes the later corpus in both arms, so exec-index replay holds only up to the first differing timeout (ADR-0005 §4). The executor ranks hang above crash, so a crash whose ASan report runs past the timeout is recorded as a hang and lost as a crash event, which biases time-to-first-crash. Mitigation, with the margin fixed before any pilot: the campaign timeout is `timeout_s` = 5.0 s, at least k = 3 (chosen 2026-11-15, before the first pilot) times D_max, the slowest crash duration of any planted bug's known trigger at the campaign concurrency; D_max was 0.195 s (bug toy-2; official run 1, commit dc54baf) before the first pilot and 0.163 s (bug mfp-1) on the candidate freeze commit 1aa932f. The floor also counts the two superseded official runs at `c` = 5 on commit 282f2ea (D_max 0.280 s, bug tlv-1, and 0.345 s, bug mfp-1; AFL-011 item (h), human decision, 2026-11-14), so it is 3 × 0.345 s ≈ 1.04 s, below `timeout_s`. At most c = 3 trials run at once, not more than the campaign machine's 10 physical cores. Monitors: the timing probe's final `hangs` on every target, in every probe trial (counted or filler, in the concurrency-1 baseline and in both official runs), expected 0, where any hang stops the freeze until the cause is found (measured per target, the higher of its two schedules' counted trials, official run 1 / run 2: toy_parser 0 / 0, tlv_parser 0 / 0, mini_format 0 / 0), and the crash-duration measurement (AFL-011). *(Added 2026-11-12, human decision.)* *(Monitor widened to every target and both runs 2026-11-13, human decision.)* *(Monitor widened to every probe trial, fillers and baseline included, 2026-11-13, human decision.)* *(Measured values filled in 2026-11-16, under AFL-011 item (j), human decision 2026-11-13; lead decision, 2026-11-16.)*
  Platform, a departure from NFR-4 (Linux + clang): the whole campaign, meaning the timing probes, the pilots and the main campaign, runs on one Mac under macOS with Homebrew LLVM's clang, not on Linux, so every result comes from that one macOS machine and nothing was measured on Linux. The machine's model, macOS version, clang version and physical core count are recorded in the campaign metadata (AFL-011). *(Added 2026-11-13, human decision.)*
  Planted bugs, a consequence of the platform: on macOS/arm64 an integer divide by zero does not trap (`sdiv` gives 0, so the run exits clean), so every planted bug in every campaign target is one that ASan reports with a stack whose `crash_site` is a target function, and none is an integer divide by zero. Every campaign target's source passes AFL-030's static source check, which holds the list of banned forms (AFL-010, AFL-016, AFL-030; pre-freeze checklist item (k), AFL-011). *(Added 2026-11-14, lead decision, 2026-11-14.)*
  Crash classification: Runs ended by a signal other than SIGSEGV or SIGABRT (e.g. SIGBUS, SIGILL, SIGFPE) are counted as crashes, following AFL's rule; only our own timeout kill is excluded (ADR-0002, AFL-018). This includes signals not raised by the target (e.g. an OS kill under memory pressure), which appear as stackless crashes. *(AFL-018, human decision 2026-11-07.)* Stackless crashes (`crash_site == "no_stack"`) cannot be matched to a planted bug, so being counted cannot change the primary endpoints, although an outside SIGKILL still changes the affected trial's own path (ADR-0003, "Stackless crashes merge under `no_stack`", point 8; AFL-030). *(Added 2026-11-15, lead decision, 2026-11-15.)*
  Crash reporters: macOS has two crash reporters, a per-user agent (`com.apple.ReportCrash`) and a system daemon (`com.apple.ReportCrash.Root`). The per-user agent was active during the first concurrency-1 baseline and the first official run 1. It used up to about 80 % of a core while tlv_parser crashed roughly 3,300 times per 10-minute trial, which slows the trials and so would bias the item (d) comparison. Those runs are superseded and not used for (d); their official D_max still counts towards the timeout floor. With only the per-user agent off, the system daemon started at the first crash and wrote reports, so that rerun was stopped and is superseded too. Both reporters were then disabled and unloaded, and a functional test (tlv_parser's trigger run 50 times through the executor) showed no crash-reporter process and no new file in either report folder. Every later run, meaning the baseline and official run 1 used for (d), the pilots and the main campaign, runs with both reporters off. This is checked by sampling processes during the runs and by the report-folder counts. Each run's metadata records both reporters' state (AFL-031). Both are turned back on after the campaign. *(Added 2026-11-15, lead decision, 2026-11-15.)*
  Core mix: the machine has 10 physical cores, 4 performance (`hw.perflevel0.physicalcpu`) and 6 efficiency (`hw.perflevel1.physicalcpu`). The OS decides which kind of core each trial runs on, so even at `c` = 3 a trial's exec/s depends on scheduling that is not under our control. Both arms run in the same waves on the same machine, so this adds variance and is not expected to favour either arm, since the arms are interleaved in the same waves. Both core counts are recorded in each run's metadata (AFL-031). *(Added 2026-11-15, lead decision, 2026-11-15.)*
  Parallel slowdown: trials that run at once share CPU, memory bandwidth and the OS's process-creation path, and every execution is a new process, so per-trial exec/s at the campaign's concurrency is below a serial run's. Each trial's budget is wall-clock time (600 s), not executions, so trials run in parallel get fewer executions. Both arms run in the same waves, so the reduction applies to both arms alike and does not favour either, but it lowers each trial's executions and so the power to detect a difference between them. Absolute numbers are also lower than a serial run would give. The baseline and official runs were taken at different times, under different background load (load averages in the AFL-011 Log), so the measured ratios in (vii) are approximate: mini_format ran faster at `c` = 3 than in the baseline. *(Added 2026-11-15, lead decision, 2026-11-15.)*

## 9. Architecture overview

Python orchestrator (corpus, mutator, scheduler, executor, metrics) drives a
separate instrumented C process per execution. Coverage crosses the boundary via
an AFL-style shared-memory edge bitmap. The experiment harness wraps the fuzzer
to run many trials and does all statistics offline from persisted metrics.
Detailed decisions are recorded as ADRs in `docs/adr/` (architect-owned).

## 10. Milestones (informational — progress tracked by the owner)

| # | Milestone | Exit criterion |
|---|---|---|
| M0 | Spike: coverage bitmap → Python | one instrumented run yields a non-empty edge set (de-risks FR-1) |
| M1 | Baseline fuzzer | UNIFORM schedule finds ≥1 toy_parser planted bug (FR-1–4, FR-10) *(was "the toy_parser bug"; changed 2026-11-07, human decision: ≥2 bugs per target)* |
| M2 | AFLFast schedule | FAST toggle implemented + unit-tested (FR-5) |
| M3 | Campaign + stats | ≥10-trial campaign with Mann-Whitney U + A12 (FR-6–9) |
| M4 | Report | figures + write-up; hypothesis evaluated honestly (G5, SC6) |

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Coverage instrumentation won't feed Python | **Spike M0 first.** Fallback: `gcov`, or wrap real AFL and focus effort on the Klees evaluation layer |
| Too little CPU/time for many long trials | Shorten budgets, fewer targets; keep trials & statistics (scale ≠ validity) |
| Null result (FAST not better) | Acceptable: report it with proper statistics; Klees-compliant null > unverified positive |
| Crash dedup overcounts | Use crash-site bucketing; disclose heuristic + bias |
| Scope creep into a "real" fuzzer | `vision.md` guards scope; non-goals are explicit |

## 12. Deliverables

- Source: `src/fuzzer/`, `targets/`, `harness/`, `tests/`.
- Reproducible experiment: `experiments/configs/main.yaml` + `results/`.
- Report (separate): intro, background (both papers), design, evaluation, threats
  to validity, conclusion.
- This repo scaffold: PRD, CLAUDE.md, crew roles, ticketing system.

## 13. References

- M. Böhme, V.-T. Pham, A. Roychoudhury. *Coverage-based Greybox Fuzzing as
  Markov Chain.* CCS 2016. → `docs/papers/aflfast-ccs2016-coverage-based-greybox-fuzzing-as-markov-chain.pdf`
- G. Klees, A. Ruef, B. Cooper, S. Wei, M. Hicks. *Evaluating Fuzz Testing.*
  CCS 2018. → `docs/papers/klees-ccs2018-evaluating-fuzz-testing.pdf`
- M. Zalewski. *American Fuzzy Lop* (tool + technical whitepaper), the baseline
  design both papers build on.
