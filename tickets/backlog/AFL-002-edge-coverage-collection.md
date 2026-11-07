---
id: AFL-002
title: Edge-coverage collection (shared-memory bitmap)
requirement: FR-1
paper_ref: AFL whitepaper (edge-coverage bitmap); mechanism per ADR-0001
module: src/fuzzer/coverage.py
depends_on: [AFL-001]
status: backlog
owner: developer
---

## Goal

Turn the AFL-001 spike into the production coverage module: after each run of an
instrumented target, the fuzzer obtains the set of hit edges and can tell whether
any of them are new relative to the global seen-set (FR-1). This is the only
feedback signal the fuzzer has; it decides retention (FR-3) and feeds path
statistics to the schedule (FR-5), never mutation (FR-4).

Open questions (PRD silent; resolve before leaving backlog):

- FR-1 says "set of hit edges". Should hit counts be kept, e.g. AFL-style
  hit-count buckets, or only edge presence? This decides what "new coverage" means.
- The PRD does not define how a "path" is identified for FAST's path-frequency
  statistic, e.g. a hash of the edge set. Does coverage.py own that identifier?
- ADR-0001 is still "proposed". This ticket assumes the shared-memory option is
  accepted after AFL-001. If AFL-001 picks a fallback, the title needs revising.

## Acceptance criteria

- [ ] Given a target built with `-fsanitize-coverage=trace-pc-guard` (via
      `make -C targets`), after one run the module returns the set of hit edges.
- [ ] The set is non-empty for any run that executes the target's `main`.
- [ ] Two inputs that drive different branches of the same target produce
      different edge sets.
- [ ] Running the same input twice produces the same edge set.
- [ ] The module reports whether a run hit ≥1 edge not in the global seen-set,
      and can add a run's edges to that seen-set.
- [ ] A run whose edges are all already in the seen-set is reported as "no new
      coverage".
- [ ] The mechanism used matches the decision recorded in ADR-0001.
- [ ] Optimization-level check (from AFL-001 spike, ADR-0001: -O1 folded a toy
      branch into branchless code and lost an edge): build `targets/tlv_parser.c`
      at the chosen optimization level and confirm its length-check branch yields a
      distinct edge, i.e. an input taking each side of the check produces differing
      edge sets. If it does not, pin targets to `-O0` in `targets/Makefile` and
      record that decision in ADR-0001.
- [ ] On a real planted-bug target (tlv_parser) built at the project's chosen
      optimization level, the length-check branch appears as a DISTINCT edge in the
      bitmap — confirming optimization does not fold real branches into branchless code.
- [ ] The optimization level for all fuzz targets is decided and recorded in ADR-0001;
      if branches do not survive the default level, targets are pinned to -O0 (as AFL
      commonly does) and that choice is documented.

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
- **Edge presence, not hit-count buckets** (proposed default — confirm). FR-1 says
  "set of hit edges", so new coverage means ≥1 edge never seen before. Disclose the
  deviation from AFL's buckets as a threat to validity.
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

## Log

- 2026-11-07 — created (req-engineer)
- 2026-11-07 — AC added from AFL-001 spike (ADR-0001)
