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
- **SC4.** `aggregate.py` reports, per metric: median + IQR, Mann-Whitney U
  p-value, and Vargha-Delaney A12 effect size.
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
| **FR-5** | Power schedules | `assign_energy(seed, corpus)` returns an int; `UNIFORM` returns a constant; `FAST` returns energy increasing with seed selection count and decreasing with path frequency (AFLFast exponential form) | `schedule.py` |
| **FR-6** | Detect & de-duplicate crashes | Crashing inputs saved with signal + faulting context; dedup buckets by crash site (PC / top-of-stack hash); dedup heuristic documented | `executor.py`, `dedup.py` |
| **FR-7** | Run campaigns | From a YAML config, run N trials × targets × schedules; trial i uses `base_seed + i`; writes per-trial time-series metrics | `run_campaign.py` |
| **FR-8** | Record & plot metrics over time | Logs edges, unique crashes, and time-to-first-crash vs. wall-clock; plots with variance bands | `fuzzer.py`, `plots.py` |
| **FR-9** | Statistical analysis | Median + IQR; Mann-Whitney U (report U, p); A12 effect size; comparison table UNIFORM vs FAST | `aggregate.py` |
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
- **Analysis:** per metric, median + IQR; Mann-Whitney U at α=0.05; A12 effect
  size for practical significance; plots with variance bands.
- **Crash dedup:** by crash site; the heuristic is named and its known
  overcounting bias acknowledged (per Klees).
- **Hypothesis (H1):** FAST ≥ UNIFORM on coverage and unique crashes, and ≤ on
  time-to-first-crash, with p < 0.05 on at least one metric/target.
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
  a harness artifact.

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
