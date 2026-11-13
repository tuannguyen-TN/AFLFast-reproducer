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
| **FR-1** | Collect edge coverage from an instrumented target | Given a target built with `-fsanitize-coverage=trace-pc-guard`, after a run the fuzzer obtains the set of hit edges and can tell if any are new vs. the global seen-set | `coverage.py` |
| **FR-2** | Execute a target on one input safely | Runs target on stdin/file input, enforces a timeout, returns (exit status, terminating signal, coverage); SIGSEGV/SIGABRT classified as crash | `executor.py` |
| **FR-3** | Manage the seed corpus | A candidate is retained **iff** it reveals ≥1 new edge; each seed stores metadata (times_selected, exec_time, size, path-frequency); corpus persists to disk | `corpus.py` |
| **FR-4** | Mutate inputs (blind) | Implements bit/byte flips, arithmetic inc/dec, interesting-value injection, havoc (stacked), and splice; mutation never reads coverage | `mutator.py` |
| **FR-5** | Power schedules | `SCHEDULES[name](seed, corpus)`, name ∈ {`uniform`, `fast`} (ADR-0004 §8), returns an int ≥ 1; `UNIFORM` returns a constant (256); `FAST`, with s = s(i) and f = f(i): for s < 16, energy = 256·min(⌊2^s/f⌋, 16), a ramp in s capped at 4096; for s ≥ 16, energy = 256·min(⌊32/next_p2(f)⌋, 16), independent of s (AFLFast afl-fuzz.c:4803-4806), so energy drops at s 15→16 for 3 ≤ f ≤ 32768; a zero factor gives 16 while the corpus holds ≤ 10 seeds, else 1. At equal s, a seed with lower f never gets less energy | `schedule.py` |
| **FR-6** | Detect & de-duplicate crashes | Crashing inputs saved with signal + faulting context; dedup buckets by crash site (PC / top-of-stack hash); dedup heuristic documented | `executor.py`, `dedup.py` |
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
  (deduped), (c) time-to-first-crash per planted bug.
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
  overcounting bias acknowledged (per Klees).
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
  skipping it above 10. From the same inputs, presence-only retention keeps a
  subset of what AFL's hit-count bucketing keeps, so our corpus tends to reach
  10 seeds later than AFL's queue would. (v) β = 1,
  following AFLFast's code (`POWER_BETA`, config.h:92); the paper's text says
  β > 1. (vi) AFL's doubling of the havoc budget when a new path is found
  (afl-fuzz.c:6576-6578) is omitted in both arms, so 4096 is a hard per-seed
  energy cap here, whereas AFL and AFLFast can exceed it. (vii) `havoc_div`
  (afl-fuzz.c:4399-4401), which shrinks the havoc budget for slow targets, is
  dropped in both arms. Our throughput of roughly 20 executions per second comes
  from executor overhead (a new process per run plus ASan start-up), not from the
  targets themselves. These parsers do almost no work per input, so under AFL's
  fork server they would almost certainly fall in the fast band, where
  `havoc_div` = 1. Their speed under a fork server was not measured. (viii) For s(i) ≥ 16, FAST's factor becomes 32 / next_p2(f(i)), independent of s(i) (AFLFast afl-fuzz.c:4803-4806), so energy drops at s(i) 15→16 for every 3 ≤ f(i) ≤ 32768 (f = 5: 4096 → 1024; f = 33: 4096 → 16 or 1). We follow AFLFast's code here, so this is not a deviation from AFLFast; it is a deviation from the paper's eq. 4 as written, whose factor 2^s(i)/f(i) has no such branch.
  Timing-dependent hangs: whether an execution hangs depends on machine load as well as on the input, and parallel trials make this worse; one differing hang changes the later corpus in both arms, so exec-index replay holds only up to the first differing timeout (ADR-0005 §4). The monitor is the pre-freeze timing probe's hang rate on toy_parser, expected to be 0 (AFL-011). *(Added 2026-11-12, human decision.)*

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
