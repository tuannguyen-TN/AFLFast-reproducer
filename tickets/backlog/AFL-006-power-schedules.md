---
id: AFL-006
title: Power schedules — UNIFORM baseline + FAST (AFLFast)
requirement: FR-5
paper_ref: AFLFast § power schedules / exponential schedule
module: src/fuzzer/schedule.py
depends_on: [AFL-004]
status: backlog
owner: developer
---

## Goal
Implement the project's independent variable: `assign_energy(seed, corpus) -> int`
with two schedules. UNIFORM reproduces vanilla-AFL equal energy; FAST implements
AFLFast's idea of more energy to seeds on low-frequency (rare) paths.

## Acceptance criteria
- [ ] `UNIFORM` returns a constant energy regardless of seed.
- [ ] `FAST` increases energy with the seed's selection count and decreases it with
      the frequency of the path it exercises (exponential form per AFLFast).
- [ ] Schedule is selected by a single parameter; **no other module** changes
      behaviour between arms (NFR-2).
- [ ] Unit tests: UNIFORM equal across seeds; FAST gives strictly more energy to a
      rare-path seed than to a high-frequency one.

## Technical notes (architect)
Pure function of seed metadata + corpus statistics; must not read coverage bitmaps
directly (keep the mutator/scheduler blind to raw edges beyond frequency stats).
See ADR on schedule interface.

## Test approach (tester)
`tests/test_schedule.py`; construct synthetic corpus states and assert energy
ordering. Later, campaign (AFL-011) checks the end-to-end effect.

## Log
- 2026-11-__ — created (req-engineer)
