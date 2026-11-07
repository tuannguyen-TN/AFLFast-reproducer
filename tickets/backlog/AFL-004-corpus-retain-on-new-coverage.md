---
id: AFL-004
title: Corpus — retain-on-new-coverage + metadata
requirement: FR-3
paper_ref: AFL whitepaper (queue / retain-on-new-coverage); AFLFast § power schedules (path-frequency metadata)
module: src/fuzzer/corpus.py
depends_on: [AFL-002, AFL-003]
status: backlog
owner: developer
---

## Goal
Keep the seed queue (FR-3). A candidate joins the corpus only if it reveals new
coverage. Each seed carries the metadata the power schedule needs. This is where
coverage feedback acts, through retention alone. It does not steer mutation.

Open questions: none. The earlier questions (f(i) definition, initial seeds,
persistence, exec_time) are resolved by the human (2026-11-07); see
`docs/adr/0004-corpus-schedule-contract.md` (ADR-0004).

## Acceptance criteria
- [ ] A candidate is retained **iff** it reveals ≥1 new edge (per AFL-002): a
      candidate with a new edge is added, and one with no new edge is not.
- [ ] Each seed stores the metadata `times_selected`, `exec_time`, `size` and
      path-frequency.
- [ ] The corpus can update a seed's `times_selected` and path-frequency as the
      loop runs.
- [ ] Retained seeds are written to disk under the run's output directory.
- [ ] Corpus behaviour is identical under UNIFORM and FAST. Nothing in corpus.py
      branches on the schedule (NFR-2).
- [ ] **f(i) counts every clean execution.** `observe()` increments the count of
      `coverage.path_id(result.edges)` on every call, whether or not the input is
      retained, and mirrors it into the matching seed's `path_freq`. Test: after a
      seed is retained, observing a non-retained clean exec with the same edge set
      increments that seed's `path_freq` by 1. Every seed has `path_freq ≥ 1`
      (the retaining run counts).
- [ ] **Clean executions only.** `observe()` raises (e.g. `ValueError`) unless
      `result.outcome == "clean"`. Test: a `"crash"` and a `"hang"` result each
      raise, and neither changes the corpus, the seen-set or any path count.
- [ ] **Selection is round-robin.** `select()` returns `seeds[k % len(seeds)]` for
      a counter `k` that advances by 1 per call, in insertion order, with no RNG.
      Because the modulo is taken on the current length, a newly retained seed
      joins the cycle. Test: with seeds A, B, calls return A, B, A; after C is
      retained, the cycle includes C. `select()` on an empty corpus raises.
- [ ] **times_selected.** A freshly retained seed has `times_selected == 0`. Only
      `mark_fuzzed(seed)` increments it, by exactly 1; `select()` and `observe()`
      never change it.
- [ ] **First retained input.** The seen-set starts empty, so the first observed
      input with ≥1 edge is always retained. A clean exec with **zero** edges
      reveals no new edge and is **not** retained (unit test: an empty-edge clean
      exec on an empty corpus leaves `seeds` empty). A target that yields zero
      edges is caught by AFL-007's "no instrumentation detected" guard, not here.
- [ ] **exec_time.** A seed's `exec_time` is the `exec_time` of the single
      execution that retained it, with no averaging.
- [ ] **Persistence is write-only.** On retention the raw bytes are written to
      `<out>/queue/id_<id:06d>`. Nothing reloads or resumes from that directory.
- [ ] **Initial seeds.** Initial seeds go through `observe()` under the same rule;
      there is no bypass and no `b""` fallback. The initial corpus is the target's
      shipped `S0` at `targets/seeds/<target>/S0` (AFL-009/010/016); reading it from
      disk and executing it is AFL-007/008/011's job, not the corpus's.

## Technical notes (architect)
- **Interfaces (`corpus.py`):**
  ```python
  @dataclass
  class Seed:
      id: int
      data: bytes
      edges: frozenset[int]
      path_id: int
      exec_time: float
      times_selected: int = 0
      path_freq: int = 0            # f(i): execs that exercised this seed's path
      @property
      def size(self) -> int: ...

  class Corpus:
      seeds: list[Seed]             # insertion order; read by schedule (AFL-006)
      def __init__(self, out_dir: Path) -> None: ...
      def observe(self, data: bytes, result: ExecResult) -> Seed | None: ...
      def select(self) -> Seed: ...
      def mark_fuzzed(self, seed: Seed) -> None: ...   # times_selected += 1
  ```
- `observe()` is the one call per clean execution. It (1) computes
  `coverage.path_id(result.edges)` and increments that path's count, then (2) retains
  the input iff `coverage.has_new_edges(result.edges, self.seen)` and adds its edges
  to `seen`. The corpus owns the global seen-set.
- **f(i)** (confirmed (human, 2026-11-07; ADR-0004)): count **every** clean
  execution, like AFLFast's `n_fuzz`, keyed by `path_id` over the presence edge set.
  Keep a `dict[int, int]` of counts for all paths, plus a `dict[int, Seed]` mirror
  (path_id → retained seed) used to update `Seed.path_freq` in O(1). A retained seed
  has a unique edge set, so seeds and paths map 1:1. The count includes the run that
  retained the seed, so it is ≥1 and FAST never divides by zero.
- **Selection** (confirmed (human, 2026-11-07; ADR-0004)): round-robin over `seeds`
  in insertion order (AFL queue cycling), with no RNG. It is identical in both arms
  by construction (NFR-2). `times_selected` is bumped by `mark_fuzzed()` after the
  seed's energy is spent, so the first energy is computed with s(i)=0.
- **Initial seeds** (confirmed (human, 2026-11-07; ADR-0004)): they go through
  `observe()` under the same rule. The initial corpus is the target's shipped `S0`
  (`targets/seeds/<target>/S0`). No `b""` fallback.
- **exec_time** (confirmed (human, 2026-11-07; ADR-0004)): taken from the single run
  that retained the seed, with no averaging.
- **Persistence** (confirmed (human, 2026-11-07; ADR-0004)): write-only. On
  retention, write the raw bytes to `<out>/queue/id_<id:06d>`. No reload or resume
  (YAGNI).
- No schedule import or parameter (NFR-2). Keep seeds in a list and never iterate a
  set to make a decision (NFR-1 determinism).

## Test approach (tester)
Unit tests with synthetic edge sets: assert retain/reject on new versus seen
edges, metadata fields present and updated, and files on disk after retention.

## Log
- 2026-11-07 — created (req-engineer)
- 2026-11-07 — per human decisions (ADR-0004): depends_on += AFL-003; confirmed all
  proposed defaults; resolved open questions; added ACs for f(i) over all clean
  execs, clean-only observe(), round-robin select(), times_selected, zero-edge
  non-retention, exec_time, write-only persistence and S0 initial seeds (req-engineer)
