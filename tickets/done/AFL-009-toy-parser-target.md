---
id: AFL-009
title: toy_parser target + documented bugs
requirement: SC1
paper_ref: Klees § performance measures / ground truth (known bugs as ground truth)
module: targets/toy_parser.c
depends_on: [AFL-003]
status: done
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
- [x] `make -C targets` builds `targets/bin/toy_parser` with
      `-fsanitize-coverage=trace-pc-guard` and AddressSanitizer.
- [x] Every planted bug is documented in the source with its location, trigger
      condition and expected terminating signal or sanitizer report.
- [x] For every planted bug, a known triggering input fed on stdin makes the
      target crash as documented.
- [x] A benign input (e.g. empty, or "BUX") makes the target exit with status 0
      and no signal.
- [x] The target reads input only from stdin and performs no network or file I/O
      beyond that (NFR-6).
- [x] **Two planted bugs (human decision 2026-11-07, PRD §8).** Exactly two planted
      bugs: `toy-1` (deep, the existing "BUG" null dereference in `check`) and
      `toy-2` (shallow, new). Each has a **single crash site** in its own function.
      The two functions differ, and neither contains any other crash site, so
      AFL-013 maps each bug to its own bucket. `toy-2` is ASan-detectable. Each
      bug's source comment documents its id, function, trigger, expected
      signal/ASan report and depth class.
- [x] **Seed.** A seed input `S0` (≤ 32 bytes, `outcome == "clean"`; 4 bytes `aaaa`,
      no newline (human decision 2026-11-12)) is committed
      at `targets/seeds/toy_parser/S0` and is the only file in that directory.
      It is this target's sole initial corpus (AFL-011), and it is the same file
      the single-byte sweep and the `toy-1` staircase below are measured against.
      The `toy-1` staircase is `aaaa -> Baaa -> BUaa -> BUGa`, and `T2` is `!aaa`
      (human decision 2026-11-12).
- [x] **Seed hash.** `S0`'s line in `targets/seeds/SHA256SUMS` (`sha256sum` output,
      `<hex>  toy_parser/S0`) is committed in the same change as `S0`, and in the
      same change as any later edit to it. AFL-011's S0 pre-flight checks it.
- [x] **`toy-1` is deep (measured, via `Executor`).** No single-byte substitution of
      `S0` (every position × all 256 values) crashes at `toy-1`'s site. The source
      documents a staircase `S0 → S1 → … → Sk`, k ≥ 3, ending in a `toy-1` trigger,
      where each `Si` (i < k) is clean and `edges(S(i+1)) − edges(Si)` is non-empty.
- [x] **`toy-2` is shallow (measured, via `Executor`).** The source documents a
      trigger `T2` that differs from `S0` by exactly one byte substitution. It
      gives `outcome == "crash"`, `signal == SIGABRT`, and an ASan report whose
      first in-source frame names `toy-2`'s function.
- [x] **No undocumented crashes or hangs.** In the single-byte sweep over `S0`, every
      crash is at `toy-1`'s or `toy-2`'s site and no result is `"hang"`.
- [x] **Ground truth.** `toy-1` and `toy-2` each have an entry (`target`, `function`,
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
Tester runs `pytest -m slow` (the depth sweeps) as a required step.

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
- 2026-11-07 — added S0 integrity pre-flight AC (human decision) (req-engineer)
- 2026-11-12 — implemented (developer). `toy-2` = shallow heap-buffer-overflow in `scan()`
  (trigger: first byte `!`); `toy-1` unchanged in `check()`, now documented as deep. S0 = `a`
  (1 byte, sha256 ca978112...48bb), staircase `a`->`B`->`BU`->`BUG`, T2 = `!`. Added
  `-fno-omit-frame-pointer` to `REQUIRED_FLAGS` in targets/Makefile (applies to all targets via the
  pattern rule, intended). Sweep (256 execs) ~28 s: only crash is `scan`, no hangs. S0 kept at 1
  byte to bound that runtime (4-byte S0 took 108 s). Retuning/freeze AC left unchecked: it is
  pending AFL-011 pilots. Fuzzer discovery is verified under AFL-007.
- 2026-11-12 — review: changes requested, back to in-progress (reviewer). The target itself
  meets every AC (reviewer re-measured through `Executor`: each staircase step adds exactly 1 new
  edge, a->B, B->BU, BU->BUG; T2 crashes in `scan` with heap-buffer-overflow/SIGABRT; fresh
  `make -C targets` into a scratch BIN dir builds all three with the new flag; ruff, mypy and
  pytest are green, 95 passed). The bounce is about the tests, which AFL-011 ("After a retune.
  Every AC of the target's ticket still passes") relies on to re-verify this ticket:
  1. `tests/test_toy_parser.py::test_toy1_deep` checks the last staircase step as
     `last.edges - seen`, where `seen = edges(S0)`. The AC requires `edges(S(i+1)) - edges(Si)`
     non-empty for every i < k, including i = k-1, so S3 must be compared with S2 (`b"BU"`), not
     with S0. With the S0 baseline, a retune that makes S3 add nothing over S2 still passes. Fix:
     compare against `ex.run(STAIRCASE[-2]).edges` (or fold S3 into the pairwise loop and allow
     only the last element to be `"crash"`).
  2. AC "known triggering input ... crash as documented": toy-1's documented report is ASan
     `SEGV on unknown address`, but the test asserts only the signal and the site. Add
     `b"SEGV on unknown address" in r.stderr`, matching what `test_toy2_shallow` already does for
     `heap-buffer-overflow`.
  Non-blocking (no change required here): (a) stale local `targets/bin/tlv_parser` and
  `targets/bin/spike` predate the `-fno-omit-frame-pointer` change, because binaries do not
  depend on the Makefile. Do a clean build (`make -C targets clean all`) before any AFL-011 pilot.
  (b) Retuning and freeze AC: leaving it unchecked is correct. Crew-lead has to decide whether
  AFL-009 can close with it carried by AFL-011.
- 2026-11-12 — human decision: S0 is 4 bytes `aaaa` (0x61616161), not 1 byte. Toy-1 becomes a
  pure substitution staircase `aaaa -> Baaa -> BUaa -> BUGa`, the same shape as AFLFast §3.2
  Listing 2, so deep-bug reachability does not hinge on our project-chosen <=32-byte insert
  limit. T2 = `!aaa`. Depth sweeps are slow tests (`@pytest.mark.slow`, excluded by default
  addopts, run with `pytest -m slow`). Supersedes the 1-byte S0 / `ca978112...` hash above.
- 2026-11-12 — rework (developer). Reviewer fixes: (1) `test_toy1_deep` now compares every
  staircase step's edges with the step before it (no S0 baseline); (2) toy-1 trigger test asserts
  `SEGV on unknown address` in stderr. Human decisions applied: S0 = `aaaa` (printf, no newline),
  sha256 `61be55a8e2f6b4e172338bddf184d6dbee29c98853e0a0485ecee7f27b9af0b4`, SHA256SUMS
  regenerated; toy_parser.c comments only updated (bug logic unchanged); sweep marked slow,
  marker registered and `-m "not slow"` added to addopts in pyproject.toml. `scan()` toy-2
  allocation is already freed on the non-crashing path (reviewer verified); left unchanged.
  Gates: ruff clean, mypy clean, `94 passed, 1 deselected in 7.51s`; `pytest -m slow`:
  `1 passed, 94 deselected in 101.72s`. Retuning/freeze AC still pending AFL-011.
- 2026-11-12 — re-review: approved, moved to testing (reviewer). Fix 1: `test_toy1_deep` checks
  every step with `pairwise(runs)`, `cur.edges - prev.edges`, and only the last step may crash.
  Fix 2: `SEGV on unknown address` is asserted. Re-measured on S0 = `aaaa` through `Executor`
  (fresh scratch build): aaaa->Baaa->BUaa->BUGa, each step adds exactly 1 edge, S0..S2 clean,
  BUGa crashes in `check`. `!aaa` gives crash, SIGABRT, heap-buffer-overflow, site `scan`. The
  4x256 sweep passes (`pytest -m slow`: 1 passed, 94 deselected in 99.47s), so nothing crashes
  in `check` and nothing hangs. Per-mutant odds with the real `mutate()` (200k each):
  aaaa->B* 2.6e-3, Baaa->BU* 3.1e-4, BUaa->BUG* 1.4e-4, aaaa->BUG directly 0. Every step is a
  1-byte arith substitution ('a'-31, -12, -26). toy_parser.c changed only in comments since the
  first review. Makefile and ground_truth.json are unchanged. pyproject registers `slow` (passes
  with `--strict-markers`), and the default run deselects only `test_single_byte_sweep`.
  Gates: ruff `All checks passed!`, mypy `Success: no issues found in 8 source files`, pytest
  `94 passed, 1 deselected`. The done-gate's `python -m pytest -q` exits 0. Retuning/freeze AC
  correctly still open, pending AFL-011.
- 2026-11-12 — verified on clean clone, ready to close (tester). Clone of 2d55468 plus only the 7
  AFL-009 paths; pytest imports the clone's `src/`. `make -C targets clean all` exit 0 with
  `-O0 -fno-omit-frame-pointer -fsanitize=address -fsanitize-coverage=trace-pc-guard`. Gates: ruff
  `All checks passed!`; mypy `Success: no issues found in 8 source files`; pytest
  `94 passed, 1 deselected` x3 (no flakes; only `test_single_byte_sweep` deselected);
  `pytest -m slow` `1 passed, 94 deselected in 43.42s`. `shasum -c` OK; S0 = `61616161`, 4 bytes.
  Independent checks (binary directly and via `Executor`): `BUG`/`BUGa` SIGABRT, ASan SEGV, #0
  `check` line 25; `!aaa` SIGABRT, heap-buffer-overflow, #0 `scan` line 38; `""`, `BUX`, S0 clean.
  Staircase adds exactly 1 edge per step, S0..S2 clean. Own 4x256 sweep: one crash, `scan:38`,
  0 hangs. Retuning/freeze AC still open and carried by AFL-011; not a blocker for closing.
- 2026-11-12 — DoD verified, moved to done (crew-lead). ruff `All checks passed!`, mypy
  `Success: no issues found in 8 source files`, pytest `94 passed, 1 deselected`; `shasum -c`
  OK (S0 = `aaaa`); ground_truth.json maps toy-1 -> `check`, toy-2 -> `scan`. Retuning/freeze AC
  intentionally still open: decided not blocking, because it is carried by AFL-011 AC
  "Pre-registered target retuning rule and freeze" (its "After a retune" bullet logs any retune
  with first-pilot numbers in this ticket's Log, and its "Freeze" bullet records the freeze hash
  here). The commit must still reference AFL-009 (human's step).
