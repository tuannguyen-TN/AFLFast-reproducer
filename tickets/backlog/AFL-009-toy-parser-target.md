---
id: AFL-009
title: toy_parser target + documented bugs
requirement: SC1
paper_ref: Klees § performance measures / ground truth (known bugs as ground truth)
module: targets/toy_parser.c
depends_on: []
status: backlog
owner: developer
---

## Goal
A control target with known planted bugs. These are the ground truth for checking
that the fuzzer finds bugs (SC1) and for time-to-first-crash per planted bug
(PRD §8). `targets/toy_parser.c` already holds one planted bug, the "BUG" magic
prefix that triggers a null dereference.

Open questions (PRD silent or ambiguous; resolve before leaving backlog):
- The INDEX title says "bugs" (plural), but the source has one planted bug. How
  many planted bugs should toy_parser have? The PRD does not say.
- SC1 needs the fuzzer to discover each bug end to end. That depends on AFL-007,
  but INDEX lists no dependencies. This ticket therefore checks only that the
  target builds and a known trigger reproduces each bug. Fuzzer discovery is
  verified under AFL-007.

## Acceptance criteria
- [ ] `make -C targets` builds `targets/bin/toy_parser` with
      `-fsanitize-coverage=trace-pc-guard` and AddressSanitizer.
- [ ] Every planted bug is documented in the source with its location, trigger
      condition and expected terminating signal or sanitizer report.
- [ ] For every planted bug, a known triggering input fed on stdin makes the
      target crash as documented.
- [ ] A benign input (e.g. empty, or "BUX") makes the target exit with status 0
      and no signal.
- [ ] The target reads input only from stdin and performs no network or file I/O
      beyond that (NFR-6).

## Technical notes (architect)
- **Expected termination:** the executor sets `ASAN_OPTIONS=abort_on_error=1`
  (AFL-003, → ADR-0002 (to write)). Under it, ASan intercepts the null dereference,
  prints `SEGV on unknown address`, and the process ends with **SIGABRT**. Without
  ASan it would end with SIGSEGV. Document both in the bug comment. Both count as
  crashes under FR-2.
- **Bug documentation:** each planted bug's comment carries a stable id
  (`PLANTED BUG toy-1`), its function, trigger and expected report. Add a
  machine-readable ground-truth file `targets/ground_truth.json` (proposed default —
  confirm), e.g. `{"toy-1": {"target": "toy_parser", "function": "check", "file":
  "toy_parser.c"}}`. dedup.py (AFL-013) reads it to map buckets to bugs for per-bug
  time-to-first-crash.
- **Number of bugs:** needs Vision/PRD decision. Note for whoever decides: with one
  bug, toy_parser's unique-crash count can never exceed 1, and per-bug TTFC has a
  single series. If bugs are added, put each in its own function so the crash sites
  are distinct for dedup, and gate them behind different depths of magic bytes so
  rare-path energy has something to find.
- **Build:** keep the Makefile flags, add `-fno-omit-frame-pointer` (proposed
  default — confirm) so dedup gets reliable ASan stack frames, and link the coverage
  runtime from AFL-002.
- **Checks:** `b"BUG"` crashes; `b""` and `b"BUX"` exit 0 with no signal. Before
  AFL-003 lands, test with plain `subprocess`; afterwards, through `Executor`.
- Stdin only, no other I/O (this already holds).

## Test approach (tester)
Build, run each documented trigger and a benign input, and assert crash or clean
exit. End-to-end discovery is covered by the AFL-007 integration test.

## Log
- 2026-11-07 — created (req-engineer)
