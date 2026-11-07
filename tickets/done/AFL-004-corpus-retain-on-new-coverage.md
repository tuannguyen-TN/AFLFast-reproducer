---
id: AFL-004
title: Corpus — retain-on-new-coverage + metadata
requirement: FR-3
paper_ref: AFL whitepaper (queue / retain-on-new-coverage); AFLFast § power schedules (path-frequency metadata)
module: src/fuzzer/corpus.py
depends_on: [AFL-002, AFL-003]
status: done
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
- [x] A candidate is retained **iff** it reveals ≥1 new edge (per AFL-002): a
      candidate with a new edge is added, and one with no new edge is not.
- [x] Each seed stores the metadata `times_selected`, `exec_time`, `size` and
      path-frequency.
- [x] The corpus can update a seed's `times_selected` and path-frequency as the
      loop runs.
- [x] Retained seeds are written to disk under the run's output directory.
- [x] Corpus behaviour is identical under UNIFORM and FAST. Nothing in corpus.py
      branches on the schedule (NFR-2).
- [x] **f(i) counts every clean execution.** `observe()` increments the count of
      `coverage.path_id(result.edges)` on every call, whether or not the input is
      retained, and mirrors it into the matching seed's `path_freq`. Test: after a
      seed is retained, observing a non-retained clean exec with the same edge set
      increments that seed's `path_freq` by 1. Every seed has `path_freq ≥ 1`
      (the retaining run counts).
- [x] **Clean executions only.** `observe()` raises (e.g. `ValueError`) unless
      `result.outcome == "clean"`. Test: a `"crash"` and a `"hang"` result each
      raise, and neither changes the corpus, the seen-set or any path count.
- [x] **Selection is round-robin.** `select()` keeps a position `_pos` and, per
      call, sets `i = _pos % len(seeds)` (length read at call time), then
      `_pos = i + 1`, and returns `seeds[i]`, in insertion order, with no RNG
      (ADR-0004 §4). It is not a monotonically growing counter taken
      `% len(seeds)`. A seed retained mid-cycle is reached before the cycle
      wraps. Test: with seeds A, B, calls return A, B, A; after C is
      retained, the cycle includes C. `select()` on an empty corpus raises.
- [x] **times_selected.** A freshly retained seed has `times_selected == 0`. Only
      `mark_fuzzed(seed)` increments it, by exactly 1; `select()` and `observe()`
      never change it.
- [x] **First retained input.** The seen-set starts empty, so the first observed
      input with ≥1 edge is always retained. A clean exec with **zero** edges
      reveals no new edge and is **not** retained (unit test: an empty-edge clean
      exec on an empty corpus leaves `seeds` empty). A target that yields zero
      edges is caught by AFL-007's "no instrumentation detected" guard, not here.
- [x] **exec_time.** A seed's `exec_time` is the `exec_time` of the single
      execution that retained it, with no averaging.
- [x] **Persistence is write-only.** On retention the raw bytes are written to
      `<out>/queue/id_<id:06d>`. Nothing reloads or resumes from that directory.
- [x] **Initial seeds.** Initial seeds go through `observe()` under the same rule;
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
- 2026-11-07 — implemented corpus.py + tests/test_corpus.py; ruff/mypy/pytest green (developer)
- 2026-11-07 — review: APPROVED -> testing. All 13 ACs verified against ADR-0004; ruff/mypy/pytest green; 9/9 targeted mutants killed. Follow-up for req-engineer: reword the round-robin AC to match ADR-0004 s4 (see Review) (reviewer)
- 2026-11-07 — reworded select() AC to the ADR-0004 §4 position form (spec-text fix per review; no decision change) (req-engineer)
- 2026-11-07 — test: PASS, ready to close. Clean-clone gates green; 13/13 ACs covered; determinism confirmed (tester)
- 2026-11-07 — DoD verified; closed (crew-lead)

## Review
Verdict: **APPROVE -> testing** (reviewer, 2026-11-07). Gates: `ruff check .`, `mypy src`, `pytest` all green.

Per-AC evidence (corpus.py line refs):
- Retain iff >=1 new edge: L47 `has_new_edges(edges, seen)`; L49 grows seen. Test `test_retain_iff_new_edge` (subset {1} rejected).
- Metadata (times_selected, exec_time, size, path_freq): Seed L15-26 matches ADR-0004 s1 exactly.
- Updatable s(i)/f(i): `mark_fuzzed` L66-67; f mirror L44-46.
- Persisted under out dir: L52-53 `<out>/queue/id_{id:06d}`, mkdir on first write.
- NFR-2: imports only coverage + executor; no schedule param or name. AST test guards imports.
- f(i) every clean exec: L43 counts before retention test; mirrored to owner; seed created with path_freq = count (=1). Test covers 1 -> 2 and an unrelated path staying 1.
- Clean only: L40 raises ValueError before any state change. Test covers crash and hang; asserts seeds, seen, path_freq and total path count unchanged.
- Round-robin: L58-64, verbatim ADR-0004 s4. Empty corpus raises RuntimeError. Test A,B,A then C -> B,C,A.
- times_selected: only `mark_fuzzed` writes it; test checks select/observe leave it at 0.
- First input / zero edges: seen starts empty; `frozenset() <= seen` is True, so a zero-edge input is not retained. Tested.
- exec_time: taken from the retaining run (L50); test confirms a later same-path run (t=9.0) does not change it.
- Write-only persistence: no read or reload path exists. Exact bytes test includes b"" and 0x00/0xff.
- Initial seeds: no bypass or b"" fallback in corpus; S0 loading is correctly left to AFL-007/008/011.

Invariants: no RNG; `seen` is only used for subset checks and union, never iterated; dicts are lookup-only (NFR-1). Mutation stays blind; corpus never touches mutator.

Test strength (throwaway mutants in a tmp copy, all killed): growing counter `k % len`; counting the path before the outcome check; no f mirror on discarded runs; f=0 at retention; retaining on a new path instead of a new edge; seen not updated; select() bumping s(i); wrong queue filename; seed_by_path not registered.

Non-blocking nits (no action required for this ticket):
- `test_non_clean_raises_and_changes_nothing` L55 repeats a SIGSEGV crash. A SIGABRT (ASan abort_on_error) case would cover the second crash signal.
- On an I/O error at L53, `seen` has already grown but the seed was not appended. A failed write ends the run anyway, so this is acceptable.

Ruling on the select() wording discrepancy: **the code is correct**. ADR-0004 s4 is the binding contract, and it explicitly forbids the "monotonically growing counter, take counter % len" form because that form re-selects or skips seeds when the length changes. The Technical notes defer to ADR-0004. The AC's test example passes, and its stated intent ("a newly retained seed joins the cycle") is met. The AC sentence "seeds[k % len(seeds)] for a counter k that advances by 1 per call" literally describes the forbidden form. **Follow-up (req-engineer):** reword that AC to the ADR form (`i = _pos % len(seeds); _pos = i + 1`; mid-cycle appends are reached before wrap) before crew-lead closes the ticket. This is a spec-text defect, not a code defect, so it does not bounce the ticket.

## Test
Verdict: **PASS (ready to close)** (tester, 2026-11-07). Status stays `testing`; crew-lead closes after the done-gate.

**Clean checkout.** `git clone` of HEAD ff306c9 into a scratch dir, plus the uncommitted `src/fuzzer/corpus.py` and `tests/test_corpus.py`. Gates were run with the repo's `.venv` tools, cwd = clone, `PYTHONPATH=<clone>/src`. The repo venv has no installed `fuzzer` package, so the import came from the clone: `fuzzer.corpus.__file__` = `<clone>/src/fuzzer/corpus.py`. Results: `ruff check .` All checks passed; `mypy src` no issues in 8 source files; `pytest` 31 passed, corpus.py 100% line coverage. The repo itself gives the same result.

**AC to test mapping.** Every AC has a test that fails if the AC breaks:
- retain iff new edge: `test_retain_iff_new_edge`.
- metadata and exec_time: `test_metadata_and_exec_time_from_retaining_run`.
- f(i) on every clean exec, and f ≥ 1: `test_path_freq_counts_non_retained_clean_exec`.
- clean only: `test_non_clean_raises_and_changes_nothing`.
- round-robin: `test_round_robin_and_new_seed_joins_cycle` checks A,B,A, then +C gives B,C,A. `test_select_empty_raises` covers the empty corpus.
- times_selected: `test_times_selected_only_via_mark_fuzzed`.
- zero edges: `test_zero_edge_clean_exec_not_retained`.
- persistence: `test_persisted_exact_bytes`.
- NFR-2: `test_corpus_does_not_import_schedule`.
- Initial seeds: covered by the absence of any bypass. S0 loading belongs to AFL-007/008/011.

**Extra mutants (scratch copy only).**
- Killed: a growing counter `_pos += 1` taken `% len`. This is the form ADR-0004 §4 forbids.
- Killed: resetting `_pos = 0` on append.
- Survived: refusing only `signal == 11` or a timeout. This is the reviewer's SIGABRT nit. The real code is correct, because it gates on `outcome != "clean"`, and a direct probe shows SIGABRT raises ValueError with the corpus unchanged. Non-blocking: a future test could add a SIGABRT case.

**Experiment validity (corpus scope).**
- NFR-1 determinism: corpus.py has no RNG and never iterates `seen` or a dict to make a decision. A 400-exec observe/select/mark_fuzzed stream gives the same SHA-256 digest of the selection order, seed metadata and seen-set under PYTHONHASHSEED=0, 1 and 12345.
- NFR-2: corpus.py does not import schedule and takes no arm parameter. Its only `schedule` matches are comments, so behaviour is the same under UNIFORM and FAST by construction.
- Persistence: the bytes written are exactly the retained bytes, named by insertion id, so they are reproducible for the same stream.

**Finding (informational, not AFL-004).** The executor classifies SIGBUS, SIGILL and SIGFPE as `clean`, so such a run would reach `observe()` and could be retained. ADR-0002 documents this ("not crashes under FR-2. Our targets do not raise them"), so it is accepted scope. The report should mention it if any target ever raises those signals.

