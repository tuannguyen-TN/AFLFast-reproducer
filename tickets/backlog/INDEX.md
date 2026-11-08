# Backlog Index

| ID | Title | Req | Module | Depends on |
|---|---|---|---|---|
| AFL-001 | Spike: coverage bitmap → Python (GO/NO-GO) | FR-1 | coverage.py | — |
| AFL-002 | Edge-coverage collection (shared-memory bitmap) | FR-1 | coverage.py | AFL-001 |
| AFL-003 | Target executor (timeout + signal capture) | FR-2 | executor.py | AFL-002 |
| AFL-004 | Corpus: retain-on-new-coverage + metadata | FR-3 | corpus.py | AFL-002, AFL-003 |
| AFL-005 | Mutation engine (flips, arith, havoc, splice) | FR-4 | mutator.py | — |
| AFL-006 | Power schedules: UNIFORM + FAST (AFLFast) | FR-5 | schedule.py | AFL-004 |
| AFL-007 | Main fuzzing loop (wire everything) | FR-1..5 | fuzzer.py | AFL-002..006, AFL-009 |
| AFL-008 | CLI | FR-10 | cli.py, pyproject.toml, README | AFL-007 |
| AFL-009 | toy_parser target + documented bugs | SC1 | targets/ | AFL-003 |
| AFL-010 | tlv_parser target + documented bugs | SC1 | targets/ | AFL-003 |
| AFL-011 | Campaign runner (N trials × targets × schedules) | FR-7 | run_campaign.py | AFL-007, AFL-009, AFL-010, AFL-016 |
| AFL-012 | Aggregation: median/IQR, Mann-Whitney U, A12 | FR-9 | aggregate.py | AFL-011 |
| AFL-013 | Crash de-duplication (crash-site bucketing) | FR-6 | dedup.py | AFL-003, AFL-007 |
| AFL-014 | Plots: coverage/crash over time + variance | FR-8 | plots.py | AFL-011 |
| AFL-015 | Track Claude hooks and settings in git | NFR (process) | .gitignore, .claude/ | AFL-001 |
| AFL-016 | Third target: mini format parser (real branch structure + deep and shallow bugs) | SC1, PRD §8 | targets/ | AFL-003 |
| AFL-017 | Corpus test: SIGABRT crash outcome rejected by observe() | FR-3 / FR-2 | tests/test_corpus.py | AFL-004 |
| AFL-018 | Classify every terminating signal as a crash (AFL rule), except our own timeout kill | FR-2 / NFR-1 | PRD FR-2, ADR-0002, executor.py, tests/test_executor.py, tests/test_corpus.py | AFL-003 |
| AFL-019 | S0 pre-flight rejects a zero-length seed (mutate(b"") can return b"") (superseded → AFL-011) | FR-7 / FR-3 / FR-4 | run_campaign.py, tests/ | AFL-011, AFL-016 |
| AFL-020 | Refresh INDEX.md status and "Suggested next pull" paragraph | NFR (process) | tickets/backlog/INDEX.md | — |
| AFL-021 | Untrack docs/.DS_Store and ignore .DS_Store everywhere (superseded → AFL-015) | NFR (process) | .gitignore | — |
| AFL-022 | Remove redundant bare-signal observe() from corpus non-clean test | FR-3 / FR-2 | tests/test_corpus.py | — |
| AFL-023 | Harden schedule purity tests: full Corpus state, attribute AST check, ban math (no file overlap with AFL-007, can run in parallel) | FR-5 / NFR-2 | tests/test_schedule.py | AFL-006 |

Status: AFL-001, AFL-002, AFL-003, AFL-004, AFL-005, AFL-006, AFL-017 and AFL-020
are done.
Unblocked now: AFL-009, AFL-010, AFL-015, AFL-016, AFL-018, AFL-022, AFL-023.
AFL-007 is blocked only on AFL-009. AFL-023 touches only tests/test_schedule.py
and can run in parallel with AFL-007. AFL-018's open question was decided by the
human (2026-11-07: every terminating signal is a crash except our own timeout
kill) and it meets DoR. AFL-018 and AFL-022 touch the same test file
(tests/test_corpus.py) and must not be worked in parallel; the second to land
rebases on the first. AFL-019 and AFL-021 are superseded (folded into AFL-011 and
AFL-015) and are not pullable.

Suggested next pull: **AFL-009** (toy_parser target), because it is now the last
unfinished dependency of AFL-007 (M1). AFL-023 can run alongside it, because the
two tickets touch different files.
