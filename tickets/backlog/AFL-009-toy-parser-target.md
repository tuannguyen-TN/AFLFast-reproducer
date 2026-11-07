---
id: AFL-009
title: toy_parser target + documented bugs
requirement: SC1
paper_ref: Klees § performance measures / ground truth (known bugs as ground truth)
module: targets/toy_parser.c
depends_on: [AFL-003]
status: backlog
owner: developer
---

## Goal
A control target with known planted bugs. These are the ground truth for checking
that the fuzzer finds bugs (SC1) and for time-to-first-crash per planted bug
(PRD §8). `targets/toy_parser.c` already holds one planted bug, the "BUG" magic
prefix that triggers a null dereference.

Open questions (PRD silent or ambiguous; resolve before leaving backlog):
- ~~The INDEX title says "bugs" (plural), but the source has one planted bug. How
  many planted bugs should toy_parser have? The PRD does not say.~~
  **Resolved (human, 2026-11-07).** PRD §8 now requires ≥2 planted bugs per
  experiment target, at distinct crash sites in distinct functions, at least one
  shallow and at least one deep, each in ground truth. toy_parser gets exactly
  two. `toy-1` (existing "BUG" staircase) is the **deep** one and the new `toy-2`
  is the **shallow** one. Why: from a seed that shares no prefix with "BUG", toy-1
  already meets the deep definition (3 byte compares, each its own edge, and no
  single substitution reaches it). So the cheapest way to get one bug of each class
  is a shallow toy-2, and toy_parser stays the easy control target. A second deep
  bug would duplicate `mfp-1`'s role (AFL-016).
- **Depth definitions** are AFL-016's "Depth definitions" section, verbatim:
  measured against the shipped seed `S0` through `Executor`. A crash is *at bug X's
  site* iff the first ASan stack frame in the target's source file names X's
  documented function. **Shallow** means ≥1 single-byte substitution of `S0`
  crashes at the site. **Deep** means no single-byte substitution of `S0` crashes
  at the site, and a documented staircase `S0 → … → Sk` (k ≥ 3, each step clean
  and adding ≥1 new edge) reaches it.
- ~~*New:* SC1 requires the fuzzer to discover **each** planted bug end to end, which
  now includes a deep bug. AFL-016's one-time retuning rule covers only `mfp-1`.
  Should the same rule (pilot: neither arm finds it, or both always find it within
  5 % of budget → retune once, then freeze) apply to `toy-1`? Needs a
  crew-lead/Vision decision.~~
  **Resolved (human, 2026-11-07).** Yes. `toy-1` falls under AFL-011's canonical
  AC "Pre-registered target retuning rule and freeze" (see the Retuning and freeze
  AC below).
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
- [ ] **Two planted bugs (human decision 2026-11-07, PRD §8).** Exactly two planted
      bugs: `toy-1` (deep, the existing "BUG" null dereference in `check`) and
      `toy-2` (shallow, new). Each has a **single crash site** in its own function.
      The two functions differ, and neither contains any other crash site, so
      AFL-013 maps each bug to its own bucket. `toy-2` is ASan-detectable. Each
      bug's source comment documents its id, function, trigger, expected
      signal/ASan report and depth class.
- [ ] **Seed.** A seed input `S0` (≤ 32 bytes, `outcome == "clean"`) is committed
      at `targets/seeds/toy_parser/S0` and is the only file in that directory.
      It is this target's sole initial corpus (AFL-011), and it is the same file
      the single-byte sweep and the `toy-1` staircase below are measured against.
- [ ] **`toy-1` is deep (measured, via `Executor`).** No single-byte substitution of
      `S0` (every position × all 256 values) crashes at `toy-1`'s site. The source
      documents a staircase `S0 → S1 → … → Sk`, k ≥ 3, ending in a `toy-1` trigger,
      where each `Si` (i < k) is clean and `edges(S(i+1)) − edges(Si)` is non-empty.
- [ ] **`toy-2` is shallow (measured, via `Executor`).** The source documents a
      trigger `T2` that differs from `S0` by exactly one byte substitution. It
      gives `outcome == "crash"`, `signal == SIGABRT`, and an ASan report whose
      first in-source frame names `toy-2`'s function.
- [ ] **No undocumented crashes or hangs.** In the single-byte sweep over `S0`, every
      crash is at `toy-1`'s or `toy-2`'s site and no result is `"hang"`.
- [ ] **Ground truth.** `toy-1` and `toy-2` each have an entry (`target`, `function`,
      `file`) in `targets/ground_truth.json`, naming different functions.
- [ ] **Retuning and freeze.** `toy-1` (deep) is governed by AFL-011's AC
      "Pre-registered target retuning rule and freeze", which is the canonical
      text. Any retune of this target, with its triggering first-pilot numbers,
      and the freeze commit hash are recorded in this ticket's Log.

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
- ~~**Number of bugs:** needs Vision/PRD decision. Note for whoever decides: with one
  bug, toy_parser's unique-crash count can never exceed 1, and per-bug TTFC has a
  single series. If bugs are added, put each in its own function so the crash sites
  are distinct for dedup, and gate them behind different depths of magic bytes so
  rare-path energy has something to find.~~ **Resolved (human, 2026-11-07):** two
  bugs, `toy-1` deep and `toy-2` shallow, in distinct functions (see Open questions
  and ACs).
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
- 2026-11-07 — resolved the number-of-bugs question (human decision: ≥2 bugs per
  target, PRD §8). Added ACs for deep `toy-1`, shallow `toy-2`, a shipped seed, the
  single-byte sweep and ground truth. Added an open question on extending the
  AFL-016 retuning rule (req-engineer)
- 2026-11-07 — per human decisions: depends_on = [AFL-003]. Added a Retuning and
  freeze pointer AC to AFL-011's canonical rule. Resolved the retune-for-toy-1
  question (req-engineer)
- 2026-11-07 — per human decision: Seed AC pins `S0` at
  `targets/seeds/toy_parser/S0`, the sole initial corpus and the file all depth
  measurements use (req-engineer)
