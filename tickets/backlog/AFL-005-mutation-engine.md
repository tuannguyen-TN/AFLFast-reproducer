---
id: AFL-005
title: Mutation engine (flips, arith, havoc, splice)
requirement: FR-4
paper_ref: AFL whitepaper (havoc, splice, operator constants); AFLFast §4.3 (deterministic-stage deferral, dropped here)
module: src/fuzzer/mutator.py
depends_on: []
status: backlog
owner: developer
---

## Goal
Make new candidates from seeds using AFL's mutation operators (FR-4). Mutation is
**blind**: it never sees coverage. Coverage acts only through retention (FR-3)
and energy (FR-5).

Open questions (PRD silent) — all resolved (human, 2026-11-07):
- ~~Ordered deterministic stages before havoc, or every operator random?~~
  **Resolved:** havoc-only in both arms, no deterministic stage. See "No ordered
  deterministic stage" in the technical notes for the rationale and the stated
  deviation from AFLFast §4.3.
- ~~Arithmetic delta range, interesting values, havoc stack depth, maximum input
  size?~~ **Resolved:** see "Constants" in the technical notes, labelled by
  provenance (AFL constant vs project choice).
- ~~How does splice pick its second input?~~ **Resolved:** from `pool`, the corpus
  seeds' raw bytes, never coverage. Confirmed acceptable.

## Acceptance criteria
- [ ] Implements bit flips.
- [ ] Implements byte flips.
- [ ] Implements arithmetic increment/decrement.
- [ ] Implements interesting-value injection.
- [ ] Implements havoc: several operators stacked on one input.
- [ ] Implements splice: combines two inputs into one candidate.
- [ ] **No deterministic stage:** mutator.py exposes no deterministic or walking
      stage; every candidate comes from `mutate()`.
- [ ] **Blind mutation (structural):** an AST test asserts mutator.py imports only
      stdlib — nothing from the `fuzzer` package (coverage, corpus, executor,
      schedule, etc.). Consequently it cannot take `Seed`/`ExecResult`: the seed
      and splice pool are raw `bytes` / `Sequence[bytes]`, so blindness is
      guaranteed by signature, not only by test.
- [ ] **Sole randomness source (NFR-1):** an AST test over the whole module (not
      just module level — inside functions too) asserts: no attribute access on
      `random` other than the `random.Random` type (so no `random.random()`,
      `random.choice`, `random.seed`, etc.); no use of `os.urandom`, `secrets`,
      `time`, `numpy.random` or `uuid`. Every function takes `rng: random.Random`
      explicitly, so the rng passed in is provably the only randomness.
- [ ] **Determinism (NFR-1):** same rng seed + same input + same pool → identical
      mutant sequence (e.g. the first 100 `mutate()` outputs); a different seed →
      a different sequence.
- [ ] Unit tests exist for mutator.py (NFR-5).

## Technical notes (architect)
- **Interfaces (`mutator.py`):** pure functions that take bytes plus an explicit RNG:
  ```python
  def bit_flip(data: bytes, rng: random.Random) -> bytes: ...
  def byte_flip(data: bytes, rng: random.Random) -> bytes: ...
  def arith(data: bytes, rng: random.Random) -> bytes: ...        # +/-1..ARITH_MAX, 8/16/32-bit
  def interesting(data: bytes, rng: random.Random) -> bytes: ...  # AFL INTERESTING_8/16/32
  def havoc(data: bytes, rng: random.Random) -> bytes: ...
  def splice(data: bytes, other: bytes, rng: random.Random) -> bytes: ...
  def mutate(data: bytes, rng: random.Random, pool: Sequence[bytes]) -> bytes: ...
  ```
  `pool` holds the corpus seeds' bytes and is used only to pick a splice partner.
  Splice reads bytes, never edges, which is acceptable (open question 3).
- **Blind:** imports only stdlib (`random`, `typing`). Never imports
  coverage/corpus/executor/schedule, and never receives an `ExecResult` or `Seed`.
- **NFR-1:** every function takes `rng` explicitly and never calls module-level
  `random.*`. The same data, RNG state and pool always give the same output.
- **No ordered deterministic stage** (confirmed (human, 2026-11-07)): every
  candidate comes from `mutate()`, so the schedule's energy is exactly the number of
  mutants and the arms differ only in energy. AFL's deterministic walk spends a
  fixed, schedule-independent budget on every seed, which would dilute the one
  variable measured and break the energy = number-of-mutants mapping. The flip,
  arith and interesting operators are still implemented and act as havoc steps.
  - **Deviation (stated):** AFLFast (Böhme et al., CCS 2016, §4.3) notes that AFL
    runs the deterministic stage the first time a seed is fuzzed; because AFLFast's
    power schedules assign far less energy initially, AFLFast defers the
    deterministic stage until the assigned energy reaches what deterministic
    fuzzing would cost. This project drops the deterministic stage in both arms, so
    energy is the only per-seed budget; the walk's operators (flips, arithmetic,
    interesting values) still run as havoc steps. Recorded in PRD §8 threats to
    validity.
  - **Expected consequence:** without the walk, magic-byte staircases (toy_parser)
    may take longer to climb. The effect is equal in both arms (no bias) but
    affects budget; watch for it in the pilot (AFL-011).
- **`mutate()`** (confirmed (human, 2026-11-07)): when `len(pool) >= 2`, splice
  with probability 1/10 against `rng.choice(pool)` first, then `havoc`. Havoc stacks
  `1 << rng.randint(1, 7)` operators (2–128, AFL's HAVOC_STACK_POW2), each drawn
  uniformly from {bit_flip, byte_flip, arith, interesting, insert_bytes, delete_bytes}.
- Insert and delete (part of AFL havoc) are required. Without them an empty or short
  seed can never grow long enough to reach "BUG" or a TLV body.
- **Constants** (confirmed (human, 2026-11-07)), labelled by provenance:
  - *AFL constants:* `HAVOC_STACK_POW2 = 7` (stack `1 << randint(1, 7)` = 2–128
    ops), `ARITH_MAX = 35`, AFL's `INTERESTING_8/16/32` sets.
  - *Project choices* (simplifications, identical across arms, **not** AFL
    constants): splice with probability 1/10 per mutant when `len(pool) >= 2` (AFL
    instead runs a separate splice stage only after a full queue cycle finds
    nothing new); a six-op uniform havoc set {bit_flip, byte_flip, arith,
    interesting, insert_bytes, delete_bytes} (AFL's havoc has more ops, e.g.
    endian-aware word/dword arith, block clone/overwrite); `MAX_INPUT = 1024` bytes.
  - *Note on `MAX_INPUT`:* toy_parser and tlv_parser read ≤512 bytes, so mutations
    beyond byte 512 yield mutants that behave like their parent (wasted execs, equal
    across arms, no bias). Revisit when AFL-016's read size is known; the value is
    unchanged.
  On empty input only length-changing ops apply; the others return the data
  unchanged.
- Blind-mutation test: parse mutator.py with `ast` and assert it has no imports from
  the package.

## Test approach (tester)
`tests/test_mutator.py`: per-operator tests (e.g. one bit flip changes exactly one
bit); an AST import test asserting mutator.py imports only stdlib and nothing from
the `fuzzer` package; a whole-module AST sole-randomness test (no `random.*`
attribute other than `random.Random`, no `os.urandom`, `secrets`, `time`,
`numpy.random` or `uuid`, inside functions too); a determinism test (same rng seed,
input and pool give identical first 100 `mutate()` outputs; a different seed gives
a different sequence); and a check that mutator.py exposes no deterministic or
walking stage.

## Log
- 2026-11-07 — created (req-engineer)
- 2026-11-07 — human decisions: havoc-only with AFLFast §4.3 deferral-vs-drop deviation; parameters confirmed with AFL-vs-project provenance; blind/sole-RNG/determinism ACs tightened (req-engineer). All open questions resolved; meets Definition of Ready (linked to FR-4/NFR-1/NFR-5 and AFLFast §4.3, objective ACs, no dependencies).
