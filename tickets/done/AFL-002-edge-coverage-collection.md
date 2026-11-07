---
id: AFL-002
title: Edge-coverage collection (shared-memory bitmap)
requirement: FR-1
paper_ref: AFL whitepaper (edge-coverage bitmap); mechanism per ADR-0001
module: src/fuzzer/coverage.py
depends_on: [AFL-001]
status: done
owner: crew-lead
---

## Goal

Turn the AFL-001 spike into the production coverage module: after each run of an
instrumented target, the fuzzer obtains the set of hit edges and can tell whether
any of them are new relative to the global seen-set (FR-1). This is the only
feedback signal the fuzzer has; it decides retention (FR-3) and feeds path
statistics to the schedule (FR-5), never mutation (FR-4).

Open questions (all resolved 2026-11-07):

- ~~Hit counts or edge presence?~~ **Resolved (human): edge presence only.** No
  hit-count buckets. Disclosed as a deviation from AFL/AFLFast (ADR-0001). Fallback
  to buckets is pre-registered in AFL-011.
- ~~Who owns path identity?~~ **Resolved (human): coverage.py**, via
  `path_id(edges) -> int`, the single seam for path identity (see notes).
- ~~ADR-0001 proposed?~~ **Resolved:** ADR-0001 accepted after AFL-001 (GO,
  shared memory). Title stands.

## Acceptance criteria

- [x] `targets/Makefile` compiles and links `targets/cov_rt.c` into the real
      targets `bin/toy_parser` and `bin/tlv_parser` (today only `bin/spike` links it),
      so `make -C targets` yields fuzz targets that write the shm bitmap.
- [x] Given a target built with `-fsanitize-coverage=trace-pc-guard` (via
      `make -C targets`), after one run the module returns the set of hit edges.
- [x] The set is non-empty for any run that executes the target's `main`.
- [x] Two inputs that drive different branches of the same target produce
      different edge sets.
- [x] Running the same input twice produces the same edge set.
- [x] The module reports whether a run hit ≥1 edge not in the global seen-set,
      and can add a run's edges to that seen-set.
- [x] A run whose edges are all already in the seen-set is reported as "no new
      coverage".
- [x] The mechanism used matches the decision recorded in ADR-0001.
- [x] Optimization level (replaces the three earlier overlapping ACs): at the
      `-O` level `targets/Makefile` uses for fuzz targets, every source-level branch in
      `targets/toy_parser.c` (the three `if`s in `check()`) and `targets/tlv_parser.c`
      (currently only `if (n < 2)`) yields a distinct edge: for each branch, an input
      taking each side produces differing edge sets. If any branch fails, pin the
      targets to `-O0` in `targets/Makefile`. Either way, record the chosen level in
      ADR-0001. (Checks the branches present at implementation time; does not depend
      on any guarding branch AFL-010 may add.)
- [x] `path_id(edges)` is the only path-identity function in the package: same edge
      set → same id across processes (no `hash()` randomisation), different sets →
      different ids. No other module derives path identity from raw edges.

## Technical notes (architect)

- **Mechanism (ADR-0001):** POSIX shared memory via stdlib
  `multiprocessing.shared_memory.SharedMemory`. Its name reaches the child in env var
  `FUZZ_SHM_NAME`. A small C runtime `targets/cov_rt.c`, linked into every target by
  the Makefile, implements `__sanitizer_cov_trace_pc_guard_init` (numbers guards
  1..N in order, maps the shm) and `__sanitizer_cov_trace_pc_guard` (`map[*guard] = 1`).
  With `FUZZ_SHM_NAME` unset the runtime does nothing, so targets still run
  standalone. Reuse what AFL-001 proved. If AFL-001 chose a fallback, only the
  `ShmBitmap` internals change, not the interface below. Accept ADR-0001 when this lands.
- **Edge = guard id.** trace-pc-guard places one guard per edge, and ids are assigned
  deterministically per binary, so edge sets compare across runs.
- **Interfaces (`coverage.py`):**
  - `MAP_SIZE = 1 << 16`
  - `class ShmBitmap`: `__init__(size: int = MAP_SIZE)`, `env() -> dict[str, str]`,
    `reset() -> None`, `edges() -> frozenset[int]`, `close() -> None` (also unlinks).
    The executor (AFL-003) owns and drives it.
  - `has_new_edges(edges: frozenset[int], seen: set[int]) -> bool`: pure; the caller
    (corpus, AFL-004) updates `seen`.
  - `path_id(edges: frozenset[int]) -> int`: stable 64-bit `hashlib.blake2b` of the
    sorted edge ids, not built-in `hash()`. This is the path identity for FAST's f(i),
    so coverage.py does own it (open question 2).
- **Edge presence, not hit-count buckets** (decided 2026-11-07). FR-1 says "set of
  hit edges", so new coverage means ≥1 edge never seen before. Deviation from
  AFL/AFLFast buckets is disclosed in ADR-0001 as a threat to validity.
- **Granularity seam.** Consumers (corpus AFL-004, schedule AFL-006, fuzzer loop)
  treat the ints from `edges()` as opaque coverage features and go through
  `has_new_edges` / `path_id` only; nobody else hashes or interprets them as guard
  ids. Switching to AFL hit-count buckets (AFL-011 fallback) then touches only
  `cov_rt.c` (`map[*guard]++`, u8 saturating) and `coverage.py` (`edges()` emits
  `guard_id * 8 + bucket(count)` with AFL buckets 1,2,3,4-7,8-15,16-31,32-127,128+);
  `has_new_edges`, `path_id` and all callers are unchanged.
- **Makefile.** Generalise the spike rule so `$(BIN)/%` links `cov_rt.c` for
  toy_parser and tlv_parser too; spike stays pinned at `-O0`.
- `edges()` uses numpy `flatnonzero` over the buffer (numpy is already pinned). A
  pure-Python scan of 64 KiB on every exec would sink NFR-3.
- coverage.py imports nothing else from the package and knows nothing about
  schedules or mutation.
- Dependency: executor.py consumes this module, so AFL-003 actually depends on
  AFL-002. INDEX lists none (req-engineer to fix).
- Platform: POSIX shm works on Linux and macOS. The dev machine is macOS and NFR-4
  says Linux, so check both.
- Per ADR-0001 (AFL-001 spike): at -O1 the toy if/else collapsed to branchless code
  (one edge, not two). Verify real-target branches survive before trusting edge counts.

## Test approach (tester)

Integration test against a built target: assert non-empty, input-dependent and
repeatable edge sets, and correct new/not-new reporting against a seen-set.
Optimization AC: toy_parser input ladder `""`, `"A"`, `"B"`, `"BA"`, `"BU"`, `"BUA"`,
`"BUG"` (crashes; bitmap is read after exit) gives pairwise-distinct edge sets per
branch side; tlv_parser `"A"` vs `"AA"` for `if (n < 2)`. Unit test for `path_id`
stability (fixed expected value, so it is not process-salted).

## Log

- 2026-11-07 — created (req-engineer)
- 2026-11-07 — AC added from AFL-001 spike (ADR-0001)
- 2026-11-07 — open questions resolved per human decisions (presence only; path_id
  seam in coverage.py; ADR-0001 accepted); three -O ACs merged into one; added
  Makefile-links-cov_rt and path_id ACs; fallback wired into AFL-011 (architect)
- 2026-11-07 — DoR verified; moved to in-progress (crew-lead/orchestrator)
- 2026-11-07 — implemented (developer): coverage.py (ShmBitmap, has_new_edges, path_id), Makefile links cov_rt.c
  into all targets; AC 9: -O1 folded toy branches (A==B, BA==BU), so CFLAGS pinned to -O0 and recorded in
  ADR-0001; tests/test_coverage.py. ruff/mypy/pytest pass. Uncommitted. Moved to review.
- 2026-11-07 — reviewed (reviewer): APPROVED, all 10 ACs verified with evidence. make -B, ruff, mypy, pytest
  (6 passed, 0 skipped) green. Independently rebuilt toy_parser at -O1: A==B=[1,3], BA==BU=[1,4] (folding
  confirmed); at -O0 all 7 ladder inputs pairwise distinct, so the ladder test fails on an -O1 regression.
  tlv A=[1,2] vs AA=[1,3]. path_id fixed value recomputed by hand (11402386789778234582). close() unlinks
  (re-attach raises FileNotFoundError); reset() clears. coverage.py imports nothing from the package; mutator
  untouched; Makefile shared by both arms (NFR-2 intact). Non-blocking follow-ups: (1) `CFLAGS ?=` lets an
  env CFLAGS silently drop the -O0 pin (spike lost its explicit -O0 too); append a fixed `-O0` outside `?=`.
  (2) explicit spike rule now duplicates the pattern rule; delete. (3) ADR-0001 says -O0 is what "AFL
  setups commonly do"; afl-gcc/afl-clang default to -O3 -funroll-loops, so record -O0 as a disclosed
  deviation (both arms equal). (4) AFL-003: close() is not idempotent and skips unlink if shm.close()
  raises; executor must wrap in try/finally; measure NFR-3 at -O0. Moved to testing.
- 2026-11-07 — verified (tester): PASS, all 10 ACs. Clean copy (no targets/bin, caches, results): `make -C targets`
  built all 3 at -O0 with ASan+trace-pc-guard; ruff clean (with .claude/ excluded, which is gitignored and absent
  in a real clone), mypy clean (8 files), pytest 6 passed x4 runs, no flakes. Independent AC 9: toy ""=[1,2,3]
  A=[1,2,4] B=[1,2,5] BA=[1,2,6] BU=[1,2,7] BUA=[1,2,8] BUG=[1,2,9] (crash rc=134, bitmap still read), pairwise
  distinct; tlv A=[1,2] vs AA=[1,3]. Determinism: 7 inputs x 20 repeats identical. close() unlinks (re-attach
  raises FileNotFoundError); 300 create/close cycles clean. Standalone run without FUZZ_SHM_NAME exits 0. One
  binary serves both arms (no schedule-dependent build). path_id is the only path-identity function in src/
  and harness/. Follow-up, worse than review note (1): `CFLAGS=-O2 make` drops not only -O0 but also
  -fsanitize=address and -fsanitize-coverage (binaries silently produce empty edge sets); fix the Makefile pin
  before AFL-011, and AFL-003 should fail fast on an empty edge set for the first seed. Status: ready to close.

- Fix-ups (human-requested, pending re-verification): Makefile now keeps `CFLAGS ?= -g` and applies a mandatory `override REQUIRED_FLAGS = -O0 -fsanitize=address -fsanitize-coverage=trace-pc-guard` after `$(CFLAGS)`, so `CFLAGS=-O2 make` no longer strips -O0/ASan/coverage; redundant `$(BIN)/spike` rule removed (pattern rule covers it); ADR-0001 drops the false "as AFL setups commonly do", records -O0 as a disclosed deviation from AFLFast's `-O3` build (arms use identical binary) and notes flags are non-overridable. Status: ready to close.
- 2026-11-07 — fix-ups re-verified (crew-lead): `make -B -C targets` builds all 3 with `-g -O0 -fsanitize=address -fsanitize-coverage=trace-pc-guard`; `CFLAGS=-O2 make -n -B` yields `-O2 -O0 ...ASan...trace-pc-guard` (pin holds); spike rule gone; ADR-0001 records -O0 vs AFLFast -O3 as disclosed deviation. ruff clean, mypy clean (8 files), pytest 6 passed. All 10 ACs remain ticked. Follow-ups recorded in AFL-003.
- 2026-11-07 — DoD verified; closed (crew-lead)
