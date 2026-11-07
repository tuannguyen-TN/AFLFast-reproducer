# ADR-0001: Coverage feedback mechanism

- **Status:** accepted (AFL-001 spike: GO)
- **Date:** 2026-11-07
- **Owner:** architect
- **Related:** AFL-001, AFL-002, AFL-003, FR-1, NFR-3

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
**Option 1.** Targets are built with `-fsanitize-coverage=trace-pc-guard`.
Python creates a POSIX shared-memory bitmap (`multiprocessing.shared_memory`,
64 KiB) and passes its name to the target via env `FUZZ_SHM_NAME`. The C runtime
`targets/cov_rt.c` assigns guard ids and sets `bitmap[id] = 1` — presence only,
no hit counts yet.

Spike evidence (AFL-001, `targets/spike.c`): input `"A"` → edges `{1,2}`,
input `"B"` → edges `{1,3}` — distinct inputs yield distinct, reproducible edge sets.

**Toolchain.** Apple clang 17's ASan hangs at startup on macOS 26.5 (stuck in
`FindDynamicShadowStart`; reproduces without coverage flags; not a sandbox
artifact). Homebrew LLVM clang 23 is required on macOS. `targets/Makefile`
prefers `/opt/homebrew/opt/llvm/bin/clang` if present, else falls back to
`clang` on PATH (Linux, NFR-4). The default is guarded by `$(origin CC)` (`CC ?=`
is a no-op against make's built-in `CC`), so `make CC=...` or an exported `CC`
overrides it. Setup docs note this.

## Consequences
- Option 1 keeps fidelity to AFL/AFLFast and makes NFR-3 reachable.
- macOS builds depend on Homebrew LLVM; Linux (NFR-4) falls back to `clang` on PATH.
- **Follow-up, owned by AFL-002 — optimization vs edges.** At `-O1` the spike's
  if/else was folded branchless (one edge for both inputs), so the spike is
  pinned to `-O0`. Optimization can likewise fold real target branches (e.g.
  `tlv_parser`'s length check), silently losing edges on *both* arms and
  weakening AFLFast's rare-path premise. AFL-002 must verify that
  `tlv_parser`'s length-check branch is a distinct edge at the chosen `-O`
  level; otherwise pin all targets to `-O0` (as AFL setups commonly do) and
  record it here.
- **Follow-up, owned by AFL-003 — performance.** Spike baseline is ~24
  execs/sec (fresh ASan process + fresh shm per exec), far below NFR-3's
  ≥500 execs/sec target. AFL-003 must add a fork server and/or reuse one bitmap
  across execs (clearing it between runs). If still far below target, document
  the executor bottleneck per NFR-3 as a threat to validity.
