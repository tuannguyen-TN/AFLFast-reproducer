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

Status (2026-11-14): done and committed: AFL-001 to AFL-006, AFL-009 (2fc1381),
AFL-017, AFL-020, AFL-023, AFL-027 (5032f29) and AFL-028 (8618c7c). AFL-012's
statistics are pre-registered (1356e97); the ticket itself is still in backlog.
Done, not yet committed: AFL-007 and AFL-015, both in the next commit batch
(stop 1). AFL-018 is in review: code reviewed and tested, deferred doc edits
applied, re-review pending; it lands in stop 1 if it closes in time, else stop 2.
AFL-011's pre-registration text lands in stop 1; its implementation is next.

Build wave next (lead decision, 2026-11-14), in parallel where files are
disjoint: AFL-008, AFL-010 and AFL-016 (taking turns on the shared targets/
files: Makefile, ground truth, SHA256SUMS), AFL-013, AFL-011 implementation,
AFL-030 (option A, human decision, 2026-11-14; after AFL-013, which creates
ADR-0003), AFL-012 and AFL-014 code, and the AFL-024 draft. AFL-016 cutoff: in
`tickets/done/`, closed by the crew-lead, by 2026-11-16, 12:00 ET; its commit
lands in the next stop and the AFL-011 baseline waits for it (a late commit
never disqualifies it); else the whole sequence runs on two targets with
`--allow-fewer-targets`, and AFL-016 is not added later (lead decision,
2026-11-14; definition revised, lead decision, 2026-11-15).

Freeze set (all land before AFL-011's freeze): AFL-015, AFL-018, AFL-027,
AFL-028 and AFL-030. Off the critical path: AFL-022, AFL-026, AFL-029 (AFL-022
and AFL-018 share tests/test_corpus.py; not in parallel). AFL-019 and AFL-021
are superseded (folded into AFL-011 and AFL-015) and are not pullable.

Suggested next pull: the build wave above.
