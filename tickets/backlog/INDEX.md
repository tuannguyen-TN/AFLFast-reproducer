# Backlog Index

| ID | Title | Req | Module | Depends on |
|---|---|---|---|---|
| AFL-001 | Spike: coverage bitmap → Python (GO/NO-GO) | FR-1 | coverage.py | — |
| AFL-002 | Edge-coverage collection (shared-memory bitmap) | FR-1 | coverage.py | AFL-001 |
| AFL-003 | Target executor (timeout + signal capture) | FR-2 | executor.py | AFL-002 |
| AFL-004 | Corpus: retain-on-new-coverage + metadata | FR-3 | corpus.py | AFL-002, AFL-003 |
| AFL-005 | Mutation engine (flips, arith, havoc, splice) | FR-4 | mutator.py | — |
| AFL-006 | Power schedules: UNIFORM + FAST (AFLFast) | FR-5 | schedule.py | AFL-004 |
| AFL-007 | Main fuzzing loop (wire everything) (done; ADR-0005 committed in 4891261, code not yet committed: lands in stop 1) | FR-1..5 | fuzzer.py | AFL-002..006, AFL-009 |
| AFL-008 | CLI | FR-10 | cli.py, pyproject.toml, README | AFL-007 |
| AFL-009 | toy_parser target + documented bugs | SC1 | targets/ | AFL-003 |
| AFL-010 | tlv_parser target + documented bugs | SC1 | targets/ | AFL-003 |
| AFL-011 | Campaign runner (N trials × targets × schedules) (pre-registration text lands in stop 1; implementation next) | FR-7 | run_campaign.py | AFL-007, AFL-009, AFL-010, AFL-016 |
| AFL-012 | Aggregation: median/IQR, Mann-Whitney U, A12 (statistics pre-registered in 1356e97; code not started) | FR-9 | aggregate.py | AFL-011 |
| AFL-013 | Crash de-duplication (crash-site bucketing) | FR-6 | dedup.py | AFL-003, AFL-007 |
| AFL-014 | Plots: coverage/crash over time + variance | FR-8 | plots.py | AFL-011 |
| AFL-015 | Track Claude hooks and settings in git (done, not yet committed: lands in stop 1; freeze set) | NFR (process) | .gitignore, .claude/ | AFL-001 |
| AFL-016 | Third target: mini format parser (real branch structure + deep and shallow bugs) (cutoff: in done, closed by the crew-lead, by 2026-11-16 12:00 ET; the commit lands in the next stop and the AFL-011 baseline waits for it; else the whole sequence runs on two targets with `--allow-fewer-targets` and AFL-016 is not added later, lead decision, 2026-11-14; definition revised, lead decision, 2026-11-15) | SC1, PRD §8 | targets/ | AFL-003 |
| AFL-017 | Corpus test: SIGABRT crash outcome rejected by observe() | FR-3 / FR-2 | tests/test_corpus.py | AFL-004 |
| AFL-018 | Classify every terminating signal as a crash (AFL rule), except our own timeout kill (in review: code reviewed and tested, deferred doc edits applied, re-review pending; stop 1 if it closes in time, else stop 2; freeze set) | FR-2 / NFR-1 | PRD FR-2, ADR-0002, executor.py, tests/test_executor.py, tests/test_corpus.py | AFL-003, AFL-028 |
| AFL-019 | S0 pre-flight rejects a zero-length seed (mutate(b"") can return b"") (superseded → AFL-011) | FR-7 / FR-3 / FR-4 | run_campaign.py, tests/ | AFL-011, AFL-016 |
| AFL-020 | Refresh INDEX.md status and "Suggested next pull" paragraph | NFR (process) | tickets/backlog/INDEX.md | — |
| AFL-021 | Untrack docs/.DS_Store and ignore .DS_Store everywhere (superseded → AFL-015) | NFR (process) | .gitignore | — |
| AFL-022 | Remove redundant bare-signal observe() from corpus non-clean test | FR-3 / FR-2 | tests/test_corpus.py | — |
| AFL-023 | Harden schedule purity tests: full Corpus state, attribute AST check, ban math (no file overlap with AFL-007, can run in parallel) | FR-5 / NFR-2 | tests/test_schedule.py | AFL-006 |
| AFL-024 | Final report part 1 (M4): results-free write-up (intro, background, design, deviations, method, draft threats to validity); can start now, closes only after the AFL-011 freeze | G5, NFR-1 | docs/report/REPORT.md | AFL-011 (close gate: freeze) |
| AFL-025 | Final report part 2 (M4): results with figures, final threats to validity, conclusion | G5, SC6, NFR-1 | docs/report/REPORT.md, docs/report/figures/ | AFL-012, AFL-013, AFL-014, AFL-024 |
| AFL-026 | Close the reflection gap in schedule purity tests: static ban + attribute-set comparison + s-guarded behavioural stream (off the critical path) | FR-5 / NFR-2 | tests/test_schedule.py | AFL-023 |
| AFL-027 | De-flake test_hang_stderr_is_bytes: no timing dependence, no quarantine, 200/200 under load (done, committed 5032f29) | NFR-1 / NFR-5 | tests/test_executor.py | AFL-003, AFL-028 |
| AFL-028 | Drain stderr after the timeout kill (bounded) so a timed-out run's stderr is complete (done, committed 8618c7c) | NFR-1 / FR-2 | executor.py, tests/test_executor.py | AFL-003 |
| AFL-029 | test_toy_parser uses AFL-007's shared `seed_files` and `crash_site` (filler, off the critical path, not in the freeze set; if worked, lands before AFL-011 checklist item (b) `pytest -m slow` runs, else (b) is re-run) (human decision, 2026-11-12) | SC1 / PRD §8, FR-6 | tests/test_toy_parser.py | AFL-007, AFL-009 |
| AFL-030 | Stackless crashes from different signals merge under `no_stack` (option A decided: disclosed bias in ADR-0003, human decision, 2026-11-14; lands before the AFL-011 freeze, after AFL-013 creates ADR-0003) | FR-6 / NFR-1 | ADR-0003 + tests | AFL-007, AFL-013, AFL-018 |
| AFL-031 | Port the AFL-011 tester's scratch checks into the repo as stubbed tests, plus T2 (freeze set: lands before the AFL-011 freeze, lead decision, 2026-11-15) | FR-7 / NFR-2 | tests/test_run_campaign.py | AFL-011 |
| AFL-032 | Reproduction instructions: README Quickstart and start.sh give the real procedure (by stop 7, after the freeze hash is known; off the critical path; lead decision, 2026-11-15) | NFR-1 / NFR-4 | README.md, start.sh | AFL-011, AFL-012, AFL-014 |
| AFL-033 | Aggregate and plots: endpoint cutoff at the budget (Q10), truncated-campaign guards, lower bound for undeterminable quantiles (Q3), sentinel-free unique crashes (Q4) (analysis-only: lands before the 2026-11-19 analysis; not a pre-freeze item, not in the freeze set; lead decision, 2026-11-15) | FR-9 / FR-8 / PRD §8 | aggregate.py, plots.py, tests | AFL-012, AFL-014 |

Status (2026-11-15): stop 1 is pushed at 624ba11 (AFL-007, AFL-015, AFL-018 and
AFL-011's pre-registration text, with the 624ba11 grooming record). AFL-016 met
its cutoff: it was moved to `tickets/done/` on 2026-11-15, before the 2026-11-16
12:00 ET cutoff, so the campaign runs on three targets (toy_parser, tlv_parser and
the mini format parser) without `--allow-fewer-targets`. Done, not yet committed:
AFL-008, AFL-010 and AFL-016.

Stop-2 wave in progress (lead decision, 2026-11-15): AFL-011 implementation
(baseline mode, abort and smoke run kind), AFL-013 closing, AFL-030's added banned
forms (`__asm`, `ualarm(`, `syscall(`), and AFL-012 and AFL-014 started early.

Freeze set (all land before AFL-011's freeze): AFL-015, AFL-018, AFL-027,
AFL-028, AFL-030 and AFL-031. Also before the freeze: AFL-022, AFL-026 and
AFL-029 (AFL-022 and AFL-018 share tests/test_corpus.py; not in parallel).
AFL-032 (reproduction instructions) lands by stop 7, once the freeze hash is
known. AFL-019 and AFL-021 are superseded (folded into AFL-011 and AFL-015) and
are not pullable.

Suggested next pull: the stop-2 wave above, then AFL-031.
