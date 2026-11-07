# Backlog Index

| ID | Title | Req | Module | Depends on |
|---|---|---|---|---|
| AFL-001 | Spike: coverage bitmap → Python (GO/NO-GO) | FR-1 | coverage.py | — |
| AFL-002 | Edge-coverage collection (shared-memory bitmap) | FR-1 | coverage.py | AFL-001 |
| AFL-003 | Target executor (timeout + signal capture) | FR-2 | executor.py | AFL-002 |
| AFL-004 | Corpus: retain-on-new-coverage + metadata | FR-3 | corpus.py | AFL-002 |
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

Status: AFL-001, AFL-002 and AFL-003 are done. Unblocked now: AFL-004, AFL-005,
AFL-009, AFL-010, AFL-013, AFL-015, AFL-016 (AFL-016's only dependency, AFL-003, is
done).

Suggested next pull: **AFL-004** (corpus). It is the only unblocked ticket on the
critical path to AFL-006 → AFL-007 (M1). AFL-005 can run in parallel with it, and so
can the targets (AFL-009/010/016).
