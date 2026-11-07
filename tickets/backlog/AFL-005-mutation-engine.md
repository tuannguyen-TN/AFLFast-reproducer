---
id: AFL-005
title: Mutation engine (flips, arith, havoc, splice)
requirement: FR-4
paper_ref: AFL whitepaper (deterministic stages, havoc, splice)
module: src/fuzzer/mutator.py
depends_on: []
status: backlog
owner: developer
---

## Goal
Make new candidates from seeds using AFL's mutation operators (FR-4). Mutation is
**blind**: it never sees coverage. Coverage acts only through retention (FR-3)
and energy (FR-5).

Open questions (PRD silent; resolve before leaving backlog):
- Does the fuzzer run AFL's ordered deterministic stages (walking bit flips and so
  on) before havoc, or apply every operator randomly? AFLFast's schedule interacts
  with this, and the choice must be the same in both arms.
- The PRD does not give the arithmetic delta range, the set of interesting values,
  the havoc stack depth, or a maximum input size.
- FR-4 does not say how splice picks its second input. If it draws from the
  corpus, it only reads seed bytes, never coverage. Confirm that is acceptable.

## Acceptance criteria
- [ ] Implements bit flips.
- [ ] Implements byte flips.
- [ ] Implements arithmetic increment/decrement.
- [ ] Implements interesting-value injection.
- [ ] Implements havoc: several operators stacked on one input.
- [ ] Implements splice: combines two inputs into one candidate.
- [ ] **Blind mutation:** mutator.py reads no coverage. It does not import
      coverage.py and takes no coverage, bitmap or edge data as input.
- [ ] **NFR-1:** all randomness comes from an RNG passed in or seeded by the
      caller. The same seed and input always produce the same output sequence.
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
- **No ordered deterministic stage** (proposed default — confirm): every candidate
  comes from `mutate()`, so the schedule's energy is exactly the number of mutants and
  the arms differ only in energy. A deterministic walk would spend a fixed,
  schedule-independent budget per seed and dilute the variable. The flip, arith and
  interesting operators are still implemented and act as havoc steps.
- **`mutate()`** (proposed default — confirm): when `len(pool) >= 2`, splice with
  probability 1/10 against `rng.choice(pool)` first, then `havoc`. Havoc stacks
  `1 << rng.randint(1, 7)` operators (2–128, AFL's HAVOC_STACK_POW2), each drawn
  uniformly from {bit_flip, byte_flip, arith, interesting, insert_bytes, delete_bytes}.
- Insert and delete (part of AFL havoc) are required. Without them an empty or short
  seed can never grow long enough to reach "BUG" or a TLV body.
- **Constants** (proposed default — confirm): `ARITH_MAX = 35`, AFL's interesting
  8/16/32-bit sets, `MAX_INPUT = 1024` bytes (the targets read ≤512). On empty input
  only length-changing ops apply; the others return the data unchanged.
- Blind-mutation test: parse mutator.py with `ast` and assert it has no imports from
  the package.

## Test approach (tester)
`tests/test_mutator.py`: per-operator tests (e.g. one bit flip changes exactly one
bit), a determinism test under a fixed seed, and a static check that mutator.py
does not import coverage.

## Log
- 2026-11-07 — created (req-engineer)
