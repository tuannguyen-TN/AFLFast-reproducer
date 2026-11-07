---
id: AFL-004
title: Corpus — retain-on-new-coverage + metadata
requirement: FR-3
paper_ref: AFL whitepaper (queue / retain-on-new-coverage); AFLFast § power schedules (path-frequency metadata)
module: src/fuzzer/corpus.py
depends_on: [AFL-002]
status: backlog
owner: developer
---

## Goal
Keep the seed queue (FR-3). A candidate joins the corpus only if it reveals new
coverage. Each seed carries the metadata the power schedule needs. This is where
coverage feedback acts, through retention alone. It does not steer mutation.

Open questions (PRD silent; resolve before leaving backlog):
- The PRD does not say how "path-frequency" is defined or counted. AFLFast's f(i)
  is the number of generated inputs that exercise path i. Do we count all
  executions or only retained ones, and how is a path identified (see AFL-002)?
- The PRD does not cover the initial seed corpus: where it comes from, and whether
  initial seeds bypass the new-edge rule.
- "Corpus persists to disk": is writing enough, or must a corpus also be reloaded
  and resumed? No on-disk format is specified.
- The PRD does not say how `exec_time` is measured (one run or averaged).

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
- `observe()` is the one call per non-crash, non-timeout execution. It (1) computes
  `coverage.path_id(result.edges)` and increments that path's count, then (2) retains
  the input iff `coverage.has_new_edges(result.edges, self.seen)` and adds its edges
  to `seen`. The corpus owns the global seen-set.
- **f(i)** (proposed default — confirm, → ADR-0004 (to write)): count **every**
  execution, like AFLFast's `n_fuzz`, keyed by `path_id` over the presence edge set.
  Keep a `dict[int, int]` of counts for all paths and mirror the count into
  `Seed.path_freq`. A retained seed has a unique edge set, so seeds and paths map 1:1.
  The count includes the run that retained the seed, so it is ≥1 and FAST never
  divides by zero.
- **Selection** (proposed default — confirm): round-robin over `seeds` in insertion
  order (AFL queue cycling), with no RNG. It is identical in both arms by construction
  (NFR-2). `times_selected` is bumped by `mark_fuzzed()` after the seed's energy is
  spent, so the first energy is computed with s(i)=0.
- **Initial seeds:** they go through `observe()` under the same rule, and the first is
  always retained because the seen-set starts empty (proposed default — confirm).
  *Which* seeds to use is methodology (Klees shows seed choice changes outcomes):
  needs Vision/PRD decision. The mechanical fallback is a single empty input `b""`.
- **exec_time** (proposed default — confirm): taken from the single run that retained
  the seed, with no averaging.
- **Persistence** (proposed default — confirm): write-only. On retention, write the
  raw bytes to `<out>/queue/id_<id:06d>`. No reload or resume (YAGNI).
- No schedule import or parameter (NFR-2). Keep seeds in a list and never iterate a
  set to make a decision (NFR-1 determinism).

## Test approach (tester)
Unit tests with synthetic edge sets: assert retain/reject on new versus seen
edges, metadata fields present and updated, and files on disk after retention.

## Log
- 2026-11-07 — created (req-engineer)
