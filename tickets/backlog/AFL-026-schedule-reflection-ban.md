---
id: AFL-026
title: Close the reflection gap in schedule purity tests (static ban + attribute-set comparison + s-guarded behavioural stream)
requirement: FR-5, NFR-2 (arms differ only in schedule.py)
paper_ref: n/a (test hardening; contract in ADR-0004 §1 and §8)
module: tests/test_schedule.py (only; no change to src/)
depends_on: [AFL-023]
status: backlog
owner: developer
---

## Goal
Close the gap where `src/fuzzer/schedule.py` could reach the corpus through
reflection and no test would notice. The AFL-023 reviewer found that
`if s > 100: getattr(corpus, 'select')()` inside `fast()` gets past every current
test: the AST attribute check (AFL-023 AC2) sees no `ast.Attribute` node, the
call's `func` is a `Call`, not an `Attribute`, and `getattr` is not banned; and the
behavioural stream (AFL-023 AC1) never calls `fast()` with s > 100, so the guarded
branch never runs. Such a mutant would advance `corpus._pos` in the FAST arm only,
a silent NFR-2 break.

A second gap is that `full_state()` compares five fixed fields, so
`setattr(corpus, "_extra", 1)` changes state the comparison never looks at.

This ticket closes both gaps in three parts. **(a)** A dynamic-access ban covers
reflective *reading* and *writing*. **(b′)** An attribute-set comparison catches
*added attributes*, even ones the static list misses. **(b)** High-s rounds cover
*unreached branches*, so guarded code actually runs.

Off the critical path. Only `tests/test_schedule.py` changes; `src/` is not
touched.

## Acceptance criteria
- [ ] **(a) Static reflection ban.** A whole-module AST test over schedule.py
      (inside functions too) fails if any of these appears:
      `getattr`, `setattr`, `delattr`, `vars`, `eval`, `exec`, `globals`,
      `__import__`, `importlib`, `__dict__`, `operator.attrgetter`,
      `operator.methodcaller`. A name counts as appearing if it is an `ast.Name`
      id, an `ast.Attribute` attr, an `Import` name (first dotted component), an
      `ImportFrom` module (first dotted component) or an `ImportFrom` imported
      name. So `from operator import attrgetter`, `from operator import
      methodcaller`, `operator.attrgetter(...)`, `builtins.getattr(...)` and
      `corpus.__dict__` all fail. `from operator import *` also fails. The real
      schedule.py passes.
- [ ] **(a′) Separate constant.** The ban list is its own constant (e.g.
      `REFLECTION_BANNED`) used by its own test. AFL-023's `BANNED` literal is
      unchanged character for character (AFL-023 AC3 pins it as exactly ten
      members).
- [ ] **(b) Behavioural: s-guarded branches run.** AFL-023's scripted stream in
      `test_schedules_leave_corpus_state_untouched` is extended with rounds whose
      selected seed has `times_selected` equal to each of **0, 15, 16, 100 and
      10**6** at the time of the energy call, so a branch guarded on `s` actually
      runs. For those rounds `len(corpus.seeds) >= 2` at the call. The test records
      `s` per F call and asserts all five values occur. AFL-023's assertions hold
      across the whole extended stream: after every step, the full corpus state of
      U and of F equals that of R (`seeds`, `seen`, `_path_count`,
      `_seed_by_path`, `_pos`), and AFL-023's (i)–(iv) still hold.
- [ ] **(b′) Attribute-set comparison.** After every step of the (b) stream (the
      AFL-023 phases and the new high-s phase), the test also compares the
      attribute-name sets of U and F against R: `set(vars(c))` for the Corpus, and
      `set(vars(x))` for every Seed object the test already compares (each seed in
      `c.seeds` and each value in `c._seed_by_path`, in order). Any attribute added
      by the schedule makes a difference and fails the test with a "fast diverged
      from R" or "uniform diverged from R" style message, even if the static ban in
      (a) misses the mechanism.
- [ ] **(c) Mutants, each required to fail.** Each is applied to a throwaway copy
      of schedule.py outside the repo (deleted afterwards, module path verified as
      in AFL-023 AC4). The developer records each mutant and the failing test name
      in the Log; the reviewer re-runs them.
      - **M-guard:** `if s > 100: getattr(corpus, 'select')()` inserted in `fast()`
        after `s, f` are read. It makes the (b) test fail **with the static ban
        disabled** (the (a) test deselected or skipped for this run), with a
        "fast diverged from R" style message.
      - **M-extra:** `setattr(corpus, "_extra", 1)` inserted in `fast()`, in two
        variants: unguarded, and guarded by `if s > 100:`. With the (a) test
        disabled (deselected or skipped for this run), each variant makes the (b′)
        comparison fail. Apply the same procedure to
        `setattr(seed, "_extra", 1)`, so the seed-level comparison is also shown to
        bite.
      - **One mutant per banned name**, each making the (a) test fail with a
        message naming the line: `getattr`, `setattr`, `delattr`, `vars`, `eval`,
        `exec`, `globals`, `__import__`, `importlib` (`import importlib`),
        `__dict__` (`corpus.__dict__`), `operator.attrgetter` (both
        `import operator` + `operator.attrgetter(...)` and `from operator import
        attrgetter`), `operator.methodcaller` (both forms).
      - The unmodified schedule.py passes every test in the file.
- [ ] **(d) Scope.** Under `src/`, `tests/`, `harness/`, `targets/` and `docs/`,
      the diff changes only `tests/test_schedule.py` (ticket and board files
      excepted). Existing tests keep their intent; `make_corpus`, `snap`,
      `full_state` and the AFL-023 tests are not weakened. `ruff check . && mypy
      src && pytest` pass.

## Technical notes (architect)
- Contract: ADR-0004 §1 (schedule.py never assigns Seed fields, appends, reorders
  or calls a mutating Corpus method) and §8 (pure function, no RNG). AFL-023 AC1
  and AC2 enforce it; this ticket closes their shared blind spot: dynamic access
  that is both invisible to the AST attribute check and gated off the stream.
- **(a) implementation.** Model on `check_no_rng_or_clock` in the same file: one
  `check_no_reflection(src: str)` walking `ast.walk(ast.parse(src))` over
  `Name`, `Attribute`, `Import` and `ImportFrom`, plus a test that applies it to
  `SRC.read_text()`. Taking `src` as a string lets the per-name mutants be
  checked as strings, without importing a broken module. Use bare names in the
  set (`attrgetter`, `methodcaller`, not dotted), so both the attribute form and
  the from-import form match. schedule.py today uses none of these names (its
  calls are `min`, `next_p2`, `len`; its imports are `collections.abc` and
  `fuzzer.corpus`), so there is no false positive.
- **(b) implementation.** Reaching s = 10**6 through `mark_fuzzed` is infeasible,
  so the test sets s directly: in a new phase after AFL-023's phase C (len 12),
  for each s in (0, 15, 16, 100, 10**6), one round does `seed = c.select()`, then
  `seed.times_selected = s` **in all three runs R, U and F identically**, then the
  energy call (none in R), then `c.mark_fuzzed(seed)`. The write is a test-side
  action applied equally to R, so the R comparison still isolates the schedule.
  Compare full state after every step, as AFL-023 does.
- **(b′) implementation.** Add the attribute-name sets either as a sibling helper
  (e.g. `attr_sets(c)` returning `(set(vars(c)), [set(vars(x)) for x in c.seeds],
  {k: set(vars(v)) for k, v in c._seed_by_path.items()})`) compared next to
  `full_state`, or as extra elements of `full_state`'s tuple. Either is fine as
  long as no existing element is removed. `Seed` is a plain `@dataclass` without
  `slots`, so `dataclasses.asdict` (used by `snap`) ignores attributes added with
  `setattr`, and `vars(seed)` catches them. The test file may use `vars`; the (a)
  ban applies only to schedule.py.
- **Why `len >= 2`.** `Corpus.select()` sets `_pos = (_pos % len) + 1`. With one
  seed an extra `select()` leaves `_pos` at 1, so it is invisible (AFL-023
  technical notes, mutant reach). With two or more seeds any extra `select()`
  changes `_pos`, so M-guard diverges from R at the s = 10**6 round.
- **Residual gap (stated, not closed).** `__builtins__["getattr"]`, `locals()` and
  similar forms are not in the human's list. The (b) stream is the backstop for
  any such access that changes compared Corpus state at the tested `s` values.
  Read-only reflection (e.g. `getattr(corpus, "_pos")` used only to compute
  energy) changes no state and is caught only by (a).
- **Sequencing.** Start only after AFL-023's change to `tests/test_schedule.py` is
  committed, so this ticket's diff on the same file is separable for review.

## Test approach (tester)
Run the gates in a clean clone. Re-apply M-guard to a throwaway copy with the (a)
test deselected and confirm the (b) test fails. Re-apply M-extra (corpus,
unguarded and guarded, plus the seed variant) the same way and confirm the (b′)
comparison fails. Re-apply each per-name mutant and
confirm the (a) test fails naming the line. Confirm the unmodified schedule.py
passes. Diff `BANNED` against AFL-023 AC3 character for character. Confirm the
extended stream asserts the five `s` values and `len >= 2` at those calls. Confirm
only `tests/test_schedule.py` changed.

## Log
- 2026-11-12 — created (req-engineer) from the AFL-023 reviewer's escape finding
  (`getattr(corpus, "select")()` gated on s > 100) (human decision)
- 2026-11-12 — amended (req-engineer): new AC (b′), an attribute-set comparison
  (`set(vars(...))` on the Corpus and on the compared Seeds after every step); new
  mutant M-extra (`setattr(corpus, "_extra", 1)` in `fast()`, unguarded and
  guarded, plus a seed variant), caught with (a) disabled. Goal states the
  three-part coverage. The static ban list and the high-s seeds (0, 15, 16, 100,
  10**6) were already complete (human decision)
