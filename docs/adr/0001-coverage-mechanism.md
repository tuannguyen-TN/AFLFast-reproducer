# ADR-0001: Coverage feedback mechanism

- **Status:** proposed (to be accepted after AFL-001 spike)
- **Date:** 2026-11-__
- **Owner:** architect
- **Related:** AFL-001, AFL-002, FR-1

## Context
The fuzzer needs per-execution edge coverage from the C target, fast enough for
hundreds+ execs/sec, crossing the C→Python boundary.

## Options considered
1. **SanitizerCoverage `trace-pc-guard` + shared-memory bitmap (AFL-style)** —
   pro: fast, faithful to AFL/AFLFast, fixed-size bitmap; con: more setup (shm).
2. **`gcov`/`--coverage`** — pro: simplest to stand up; con: slow, file churn per
   run, not representative of greybox speed.
3. **File-based guard callback** — pro: trivial; con: I/O per run, slow.

## Decision
Pending AFL-001. Default to option 1; fall back to option 2/3 only if the spike
shows shared memory is impractical in the time available.

## Consequences
Option 1 makes NFR-3 (performance) achievable and keeps fidelity to the papers.
If we fall back, document the speed limitation as a threat to validity.
