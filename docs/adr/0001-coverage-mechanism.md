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

**Granularity (human decision, 2026-11-07): edge presence only.** New coverage =
≥1 never-seen edge; a path is identified by `coverage.path_id(edges)` (blake2b of
the sorted edge ids). Path identity and novelty live only in `coverage.py`;
callers treat edge ids as opaque features. Switching to AFL hit-count buckets
therefore touches only `cov_rt.c` (saturating u8 counts) and `coverage.py`
(feature = `guard_id * 8 + bucket`). The switch is pre-registered as a pilot
fallback with a measurable trigger in AFL-011, applied to both arms before the
main campaign.

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
- **Threat to validity — presence-only coverage.** AFL and AFLFast use hit-count
  buckets, so loop-iteration differences count as new coverage and as distinct
  paths. Presence-only yields fewer distinct paths, which coarsens FAST's path
  frequency f(i) and may understate its advantage. Both arms share the same
  granularity, so isolation (NFR-2) holds; the deviation is disclosed in the
  report, together with the AFL-011 pilot outcome.
- macOS builds depend on Homebrew LLVM; Linux (NFR-4) falls back to `clang` on PATH.
- **Follow-up, owned by AFL-002 — optimization vs edges.** At `-O1` the spike's
  if/else was folded branchless (one edge for both inputs), so the spike is
  pinned to `-O0`. Optimization can likewise fold real target branches,
  silently losing edges on *both* arms and weakening AFLFast's rare-path
  premise. AFL-002 must verify that every source-level branch in `toy_parser`
  and `tlv_parser` (today tlv has only `if (n < 2)`; its planted bug is the
  *missing* length check) is a distinct edge at the chosen `-O` level;
  otherwise pin all targets to `-O0`. Record the
  chosen level here: **`-O0`** (AFL-002). Evidence at `-O1`
  (edge ids, toy_parser): `""`=[1,2], `A`=`B`=[1,3], `BA`=`BU`=[1,4], `BUA`=[1,5],
  `BUG`=[1,6], so the `d[0]=='B'` and `d[1]=='U'` sides folded together; tlv `A`=[1,2]
  vs `AA`=[1,3] was distinct. Pinned `CFLAGS` to `-O0` in `targets/Makefile`;
  `tests/test_coverage.py` asserts all seven toy inputs give pairwise-distinct sets.
  `-O0`, ASan and trace-pc-guard are now non-overridable (a separate `REQUIRED_FLAGS`
  var placed after `$(CFLAGS)`; an inherited `CFLAGS` can only add extras).
  **Disclosed deviation / threat to validity:** `afl-gcc`/`afl-clang` default to
  `-O3 -funroll-loops` unless `AFL_DONT_OPTIMIZE` is set, and AFLFast used that
  default, so our `-O0` build differs from AFLFast's. Both schedule arms use the
  identical binary, so arm isolation (NFR-2) is unaffected.
- **Follow-up, owned by AFL-003 — performance.** Spike baseline is ~24
  execs/sec (fresh ASan process + fresh shm per exec), far below NFR-3's
  ≥500 execs/sec target. AFL-003 reuses one bitmap across execs (clearing it
  between runs) and documents any remaining shortfall per NFR-3 as a threat to
  validity. A fork server is conditional, decided at AFL-011 with real numbers
  (see AFL-003/AFL-011).

## Amendment 2026-11-15 (lead decision, AFL-034): hit-count buckets

**Decision.** The pre-registered granularity rule (AFL-011) fired on the first pilot
(results/pilot/first_pilot, d9a22db, seeds 2000..2002, c = 3, pooled over both arms,
n = 6 per target, final metrics.csv row): median distinct_path_ids / median corpus_size
toy_parser 4.5 / 3.5 (fires, < 20), tlv_parser 14.0 / 8.0 (fires, < 20), mini_format
65.5 / 20.0 (does not fire). The runner's results/pilot/granularity_decision.json agrees:
`trigger_fired: true`, `granularity: "hit_count_buckets"`. Coverage therefore moves from
plain edge sets to AFL hit-count buckets. This supersedes the "presence only" wording of
the Decision section for retention, `path_id` and f(i); the presence-only deviation
paragraph above is now historical.

**Mechanism.** `targets/cov_rt.c` keeps one saturating unsigned 8-bit counter per guard
(255 stays 255; it never wraps to 0 = "not hit"). `coverage.py` buckets a count AFL's way:
1, 2, 3, 4-7, 8-15, 16-31, 32-127, 128+ (stored as AFL's bit values 1, 2, 4, 8, 16, 32, 64,
128; 0 yields no pair). Corpus retention (`Corpus.seen_hits`), `path_id` (hashes the sorted
(edge, bucket) pairs) and hence f(i) use (edge, bucket) pairs. Arms are unchanged and
identical: the energy formula in `schedule.py` is untouched, but f(i)'s input semantics
change for both arms. Mutation stays blind (`mutator.py` untouched).

**Endpoint preserved; exception to "no other module changes" (AFL-011 seam AC).**
`edges` / `final_edges` (ADR-0005 s6) remain the number of distinct edge ids hit by clean
executions, not a count of pairs. This needed small changes outside the two seam files:
- `executor.py`: `ExecResult.edges` (field) becomes `ExecResult.hits` (pairs); `edges` is
  now a derived property (distinct edge ids), so every consumer of `.edges` is unchanged.
- `corpus.py`: new `seen_hits` is the retention key; `seen` stays the distinct-edge-id set
  whose `len()` is the endpoint, updated only on retention as before.
- `fuzzer.py`: the four `path_id(r.edges)` calls become `path_id(r.hits)`. `schedule.py`
  needed no change.
Effect on old data: path ids and corpus sizes from before this amendment are not
comparable with later ones; the pilot above is the pre-switch record.

**Amendment 2026-11-15, addendum (AFL-034 review round 1).**
- *`distinct_path_ids` changes meaning.* It now counts distinct (edge, bucket) sets, not
  distinct edge sets, because `path_id` hashes pairs. The AFL-011 pilot granularity rule
  reads this column, so pilot medians recorded before this amendment (the first pilot above)
  and after it are not comparable. `edges` / `final_edges` are unaffected (distinct edge ids).
- *Wording superseded.* ADR-0005 s6 ("`coverage.path_id(r.edges)`", "counts distinct edge
  sets", and the "Remaining difference from AFL ... presence only" bullet) and ADR-0004 s2
  ("(over the presence edge set, ADR-0001)") describe the pre-switch behaviour and are
  superseded by this amendment. Those ADRs are not edited here.
- *PRD follow-up (lead).* PRD deviation (iv) ("presence-only retention keeps a subset ...")
  is now stale; the PRD is not edited by AFL-034.
- *Disclosed difference from AFL.* AFL 2.x (which AFLFast builds on) wraps its 8-bit
  counters; we saturate at 255. Both arms share this.
