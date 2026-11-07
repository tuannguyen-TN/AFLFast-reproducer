# Backlog Index

| ID | Title | Req | Module | Depends on |
|---|---|---|---|---|
| AFL-001 | Spike: coverage bitmap → Python (GO/NO-GO) | FR-1 | coverage.py | — |
| AFL-002 | Edge-coverage collection (shared-memory bitmap) | FR-1 | coverage.py | AFL-001 |
| AFL-003 | Target executor (timeout + signal capture) | FR-2 | executor.py | AFL-002 |
| AFL-004 | Corpus: retain-on-new-coverage + metadata | FR-3 | corpus.py | AFL-002, AFL-003 |
| AFL-005 | Mutation engine (flips, arith, havoc, splice) | FR-4 | mutator.py | — |
| AFL-006 | Power schedules: UNIFORM + FAST (AFLFast) | FR-5 | schedule.py | AFL-004 |
| AFL-007 | Main fuzzing loop (wire everything) | FR-1..5 | fuzzer.py | AFL-002..006 |
| AFL-008 | CLI | FR-10 | cli.py | AFL-007 |
| AFL-009 | toy_parser target + documented bugs | SC1 | targets/ | AFL-003 |
| AFL-010 | tlv_parser target + documented bugs | SC1 | targets/ | AFL-003 |
| AFL-011 | Campaign runner (N trials × targets × schedules) | FR-7 | run_campaign.py | AFL-007, AFL-009, AFL-010, AFL-016 |
| AFL-012 | Aggregation: median/IQR, Mann-Whitney U, A12 | FR-9 | aggregate.py | AFL-011 |
| AFL-013 | Crash de-duplication (crash-site bucketing) | FR-6 | dedup.py | AFL-003 |
| AFL-014 | Plots: coverage/crash over time + variance | FR-8 | plots.py | AFL-011 |
| AFL-015 | Track Claude hooks and settings in git | NFR (process) | .gitignore, .claude/ | AFL-001 |
| AFL-016 | Third target: mini format parser (real branch structure + deep and shallow bugs) | SC1, PRD §8 | targets/ | AFL-003 |
| AFL-017 | Corpus test: SIGABRT crash outcome rejected by observe() | FR-3 / FR-2 | tests/test_corpus.py | AFL-004 |
| AFL-018 | Decide and disclose non-SEGV/ABRT fatal signals (SIGBUS, SIGILL, SIGFPE) classified as clean | FR-2 / NFR-1 | PRD, executor.py (possibly), report | AFL-003 |

Status: AFL-001, AFL-002, AFL-003 and AFL-004 are done. Unblocked now: AFL-005,
AFL-006, AFL-009, AFL-010, AFL-013, AFL-015, AFL-016, AFL-017. AFL-018's dependency
(AFL-003) is done, but it is **not ready** (DoR fails) until the human decides its
open question (options a/b/c).

Suggested next pull: **AFL-017** (SIGABRT corpus test), ahead of the other
non-critical-path work, because the human prioritized it. It is test-only and small.
**AFL-005** (mutation engine), already chosen by the human as the next feature
ticket, proceeds in parallel with it. AFL-006 is now unblocked on the critical path
to AFL-007 (M1).
