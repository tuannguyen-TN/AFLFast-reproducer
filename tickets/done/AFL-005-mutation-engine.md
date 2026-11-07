---
id: AFL-005
title: Mutation engine (flips, arith, havoc, splice)
requirement: FR-4
paper_ref: AFL whitepaper (havoc, splice, operator constants); AFLFast §4.3 (deterministic-stage deferral, dropped here)
module: src/fuzzer/mutator.py
depends_on: []
status: done
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
- 2026-11-07 — implemented (developer, sonnet); reviewed: BOUNCE #1 — havoc stacking untested (depth/op-set mutants survive); sole-randomness/blind AST tests evadable (import alias, getattr, __import__); unpinned AFL constants; unlabelled splice/insert deviations (reviewer)
- 2026-11-07 — bounce #1 fixes: havoc depth/op-coverage test, hardened AST bans, rng-signature test, AFL constants pinned, AFL single-cut splice, deviations labelled (developer)

## Review (reviewer)
- 2026-11-07 — Re-review after bounce #1: **APPROVE → testing**. ruff, mypy and pytest are green (test_mutator 20/20).
- All bounce #1 items (1–14) were verified fixed. INTERESTING_8/16/32, ARITH_MAX=35 and HAVOC_STACK_POW2=7 match AFL config.h, and the 16/32-bit pools include the narrower values as AFL does.
- Splice uses AFL's single cut `data[:k]+other[k:]` with 1≤k<min(len), skips when the shorter input is under 2 bytes, and is never empty. Skipping locate_diffs and allowing self-pick are labelled as project choices.
- Blind invariant: stdlib-only imports, raw bytes/Sequence[bytes] signatures, no coverage reads. Isolation (NFR-2): the mutator knows nothing about the schedule, so both arms get the same mutator.
- NFR-1: AST bans plus the injected-rng signature test, backstopped by the behavioural determinism test. Probes that reseed or clone the rng were killed.
- Should-fix (non-blocking): test the `[:MAX_INPUT]` truncation (removing it survives), and pin MAX_INPUT=1024 and SPLICE_PROB=0.1 (both changes survive; both are project choices, the same in both arms).
- Nits: add `__builtins__` to `_BANNED_NAMES`. `mutate(b"")` can return `b""`; check this against the S0 seeds in AFL-016.
- 2026-11-07 — reviewer should-fix items applied (truncation test, MAX_INPUT/SPLICE_PROB/_MAX_BLOCK pinned, __builtins__ banned); moved to testing (developer/orchestrator)

## Test (tester)
- 2026-11-07 — **GREEN → ready to close.** Clean clone at 5c531b6 plus working-tree mutator.py and test_mutator.py: ruff and mypy clean, pytest 52/52, mutator.py coverage 100%.
- All 11 ACs PASS. Blind: stdlib-only imports; `mutate(bytes, random.Random, Sequence[bytes])`. NFR-2: no schedule, energy or coverage reference in mutator.py.
- NFR-1 across processes: separate processes with PYTHONHASHSEED=1 and 2, Random(42), same input and pool. The first 100 `mutate()` outputs are byte-identical, and all 100 are distinct.
- Distribution (16 B input, 10k mutants): lengths 1–403 with no pool and 1–448 with a pool of 2; ~9.5k unique; 0 empty; ≤3 equal to the input.
- AFL spot-checks: 16-bit arith wraps inside its window; 32-bit interesting writes -1 and -128 sign-extended in both byte orders; splice uses one shared cut.
- Independent mutants: 8/12 killed (arith sign, 1-byte interesting, LE-only, depth cap, `pool[0]` partner, zero delta, constant insert block, no 32-bit width). The arith-sign and constant-block kills are indirect.
- Survivors (non-blocking, arm-neutral): bit_flip never touching bit 7; insert never at the end; delete never at the tail; 32-bit interesting pool missing the 8/16 values. Follow-up: add direct tests for these.
- 2026-11-07 — tester survivors M4/M5/M6/M8 and indirect M1/M11 killed by direct tests (developer); pytest 59 passed, mutator.py 100%
- 2026-11-07 — DoD verified, closed (orchestrator/crew-lead): reviewer approve (after bounce #1), tester green, gates green
