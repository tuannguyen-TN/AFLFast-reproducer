---
id: AFL-023
title: Harden schedule purity tests (full Corpus state, attribute AST check, ban math)
requirement: FR-5, NFR-2 (arms differ only in schedule.py)
paper_ref: n/a (test hardening)
module: tests/test_schedule.py
depends_on: [AFL-006]
status: done
owner: developer
---

## Goal
Close the two test gaps the AFL-006 tester found. schedule.py complies today, but
the suite would not catch a regression. (1) The purity test snapshots only
`corpus.seeds`. A `fast()` that called `corpus.select()` (advancing `_pos`),
wrote `corpus.seen`, or changed other Corpus state would pass. That would be a
silent divergence in the FAST arm only, breaking NFR-2. (2) `math` is not in the
banned set, although AFL-006 requires integer arithmetic with no `math`.

Scope: **only `tests/test_schedule.py` changes.** No production code, no PRD, no
ADR. These ACs belong to schedule.py, not to AFL-007, so this ticket can run in
parallel with AFL-007, which touches different files.

## Acceptance criteria
- [x] **AC1, behavioural purity (Gap 1a).** A test drives one fixed, hard-coded
      `observe` / `select` / `mark_fuzzed` stream through three fresh `Corpus`
      instances (separate `tmp_path` subdirectories). Run R, the reference, calls
      no schedule at all. Run U calls only `schedule.uniform(seed, corpus)` for
      energy after each `select()`. Run F calls only `schedule.fast(seed, corpus)`
      at the same points. After **every** step, the test asserts that the full
      corpus state of run U equals that of run R, and that the full corpus state
      of run F equals that of run R:
      `[asdict(s) for s in corpus.seeds]`, `corpus.seen`, `corpus._path_count`,
      `{k: asdict(v) for k, v in corpus._seed_by_path.items()}` and `corpus._pos`.
      Comparing each run to R, rather than U to F, also catches a side effect that
      both schedules share. Only the returned energy values may differ. The stream
      uses the real signatures `observe(data, result: ExecResult)`, `select()` and
      `mark_fuzzed(seed)`. `ExecResult` values are built directly (clean outcome:
      `exit_status=0, signal=None, timed_out=False`, chosen `edges`,
      `exec_time=0.0`, `stderr=b""`). No target is run. The test itself asserts
      that the stream reaches all of the following:
      (i) `len(corpus.seeds) > 10`;
      (ii) at least one observe that is not retained (repeat path, so
      `path_freq` > 1);
      (iii) at least one FAST call in run F where the selected seed has
      `times_selected >= 16` **at the time of the call** (recorded per call, not
      read from the end state);
      (iv) the energies returned in run F include both `16` and `1`. These values
      come only from FAST's zero-factor branch, at corpus size ≤ 10 and > 10
      respectively; every other FAST result is ≥ 256.
      Together, (iii) and (iv) put the `s < 16` and `s >= 16` branches and both
      zero-factor corpus-size branches of `fast` on the tested path.
- [x] **AC2, static attribute check (Gap 1b).** An AST test over the whole of
      schedule.py (inside functions too) asserts all of the following. Every
      `ast.Attribute` access on the `Seed` parameter reads only `times_selected`
      or `path_freq`. Every `ast.Attribute` access on the `Corpus` parameter reads
      only `seeds`, and `corpus.seeds` occurs only as the sole argument of
      `len(...)`. Every one of these allowed accesses has an `ast.Load` context,
      so a write such as `seed.times_selected += 1` (Store context) fails. No
      other name has an attribute accessed, so an alias such as
      `c = corpus; c.select()` fails. No `ast.Call` has an `ast.Attribute` as its
      `func`, so no Corpus method (or any other method) is called. The real
      schedule.py passes.
- [x] **AC3, banned set adds `math` (Gap 2).** The banned-name constant in
      tests/test_schedule.py is exactly this set, no more and no less:
      `{"random", "secrets", "numpy", "uuid", "time", "os", "urandom", "importlib", "__import__", "math"}`
      (that is: random, secrets, numpy, uuid, time, os / os.urandom, importlib,
      `__import__`, math). Import aliases (`asname`) remain banned. The delta
      against today's `BANNED` is **+`math`** only; every other member is already
      present. The test applies the set to `Import`, `ImportFrom` (module and
      names), `Name` and `Attribute` nodes, as today. The real schedule.py passes.
- [x] **AC4, proof the tests bite.** Each mutant below is applied to a throwaway
      copy of schedule.py outside the repo (deleted afterwards) and makes the named
      test fail. The developer records each mutant and the failing test name in
      the Log, and the reviewer re-runs them.
      - M1: `fast()` calls `corpus.select()` → AC1 test fails **and** AC2 test fails.
      - M2: `fast()` adds to `corpus.seen` (e.g. `corpus.seen.add(-1)`) → AC1 test
        fails **and** AC2 test fails.
      - M3: `import math` added to schedule.py → AC3 test fails.
      - M4: `seed.times_selected += 1` inside `fast()` → AC1 test fails **and**
        AC2 test fails.
- [x] **AC5, scope.** Under `src/`, `tests/`, `harness/`, `targets/` and `docs/`,
      the ticket's diff changes only tests/test_schedule.py (ticket and board
      files excepted). The existing tests in that file are kept, with the same
      intent: the table, `next_p2`, uniform constant/floor, registry and imports
      tests. `ruff check . && mypy src && pytest` pass.

## Technical notes (architect)
- Contract: ADR-0004 §1 (schedule.py never assigns Seed fields, appends,
  reorders or calls a mutating Corpus method) and §8 (pure function, no RNG).
  The amendment of 2026-11-07 narrows energy inputs to `times_selected`,
  `path_freq` and `len(corpus.seeds)`. AC2 pins exactly that.
- AC1 and AC2 complement each other. AC1 catches any effect on state, including
  dynamic access (`getattr`, aliases) that AC2 cannot see. AC2 catches a write
  that a particular stream might not reach and fails with a line number.
- AC1 reads private Corpus fields (`_path_count`, `_seed_by_path`, `_pos`). That
  is acceptable in a test that pins a cross-module contract. If corpus.py later
  renames them, this test must be updated in the same change.
- **Disk.** `Corpus.__init__` writes nothing. `observe()` writes
  `<out_dir>/queue/id_NNNNNN` on every retention (mkdir on first write). So the
  three runs need three directories: `Corpus(tmp_path / "R")`, `/ "U"`, `/ "F"`.
  `_queue_dir` differs by construction and is not part of the compared state.
- **ExecResult.** `ExecResult(exit_status=0, signal=None, timed_out=False,
  edges=frozenset(E), exec_time=0.0, stderr=b"")` (import from
  `fuzzer.executor`). Its `outcome` is `"clean"` because `timed_out` is false and
  `signal` is not in `CRASH_SIGNALS`. Use singleton edge sets `{k}`: each new `k`
  is a new edge, so the input is retained as a new seed. Repeating `{k}` is not
  retained and raises that seed's `path_freq`.
- **Stream (apply identically to R, U and F; one "round" is `seed = c.select()`;
  energy call (none in R); `c.mark_fuzzed(seed)`; each run uses its own returned
  `seed`).** FAST energies are given in brackets for this stream:
  - A: observe `{0}` (seed 0, f=1), then `{0}` twice more (not retained, f=3).
    This is (ii).
  - B: 17 rounds with `len == 1`. Seed 0 has s = 0..16 and f = 3. FAST gives
    [16, 16, 256, 512, 1280, 2560, 4096 ×10, 2048]. The 16s are the zero-factor
    branch at ≤ 10 seeds. The last call is at s = 16, the `s >= 16` branch
    (32 // next_p2(3) = 8), and shows the 15→16 drop. This is (iii).
  - C: observe `{1}` (seed 1), `{1}` again (f=2), then `{2}`…`{11}` (seeds
    2–11, len 12). This is (i). Then 12 rounds. `_pos` is 1, so the first round
    selects seed 1 (s=0, f=2), which takes the zero-factor branch at > 10 seeds
    [1]. Seeds 2–11 give [256 each]. Seed 0 (s=17) gives [2048].
  - Assert (i)–(iv) at the point of the energy call, not only at the end: record
    `(seed.times_selected, len(c.seeds))` for each F call. Also assert that
    `16 in F_energies and 1 in F_energies`. Those values come only from the
    zero-factor branch, because every other FAST result is 256 · perf // 100
    with perf ≥ 100, so ≥ 256. U energies all equal 256.
  - Mutant reach: M2 diverges from R at the first F call (B). M1 does **not**
    diverge while `len == 1`, because an extra `select()` leaves `_pos` at 1.
    It diverges at the first round of C (`_pos` 2 in R, 3 in F). So phase C with
    ≥ 2 seeds is required for M1.
- **AC2 implementation.** Walk each `FunctionDef`. Treat params annotated `Seed`
  or `Corpus` as the Seed and Corpus names. Every `ast.Attribute` must have
  `.value` as an `ast.Name` that is one of those params, with `.ctx` an
  `ast.Load`. Check `ctx` because `seed.times_selected += 1` is an Attribute with
  attr `times_selected` but a Store ctx, and an attr-only check would pass it.
  Allowed attrs are {times_selected, path_freq} on Seed and {seeds} on Corpus.
  Build a parent map (`ast` has no parent links) to check that `corpus.seeds`'
  parent is `Call(func=Name("len"), args=[it], keywords=[])`. Chains such as
  `corpus.seen.add` fail because the outer Attribute's `.value` is not a Name.
  No false positives today: schedule.py has no `bit_length` or any other method
  call. Its calls are `min`, `next_p2` and `len`, all `ast.Name` funcs. The
  annotations `Callable[[Seed, Corpus], int]` and `dict[str, EnergyFn]` are
  Subscripts, and the `collections.abc` import is an ImportFrom, so none of them
  produces an Attribute node. Its only Attribute nodes are `seed.times_selected`,
  `seed.path_freq` and `corpus.seeds` (in `fast`).
- **Scope.** The diff touches only tests/test_schedule.py: the `BANNED` literal
  (+`"math"`), one AC1 test, one AC2 test, and optionally the docstring. Do not
  change `make_corpus`, `snap` or the existing tests.
- Model for the AST style: `tests/test_mutator.py::test_sole_randomness_source_whole_module`.
- No `assign_energy` name appears in tests/test_schedule.py, so the optional
  wording tidy does not apply. The PRD FR-5 rewording is a separate task.
- The module docstring of tests/test_schedule.py may add `AFL-023` next to `AFL-006`.

## Test approach (tester)
Run the gates in a clean clone. Re-apply M1–M4 to a throwaway copy outside the
repo and confirm that each fails the named test(s). Confirm that the unmodified
schedule.py passes all of them. Diff the banned-set literal in the test against
the AC3 list character for character. Confirm that the AC1 stream assertions
(i)–(iv) are present and hold. Confirm that only tests/test_schedule.py changed.

## Log
- 2026-11-07 — created (req-engineer) from AFL-006 tester finding (human decision, 2026-11-07)
- 2026-11-07 — AC1 adds no-schedule reference run R (orchestrator decision, 2026-11-07)
- 2026-11-07 — AC1 adds call-time s>=16 and zero-factor 16/1 checks; AC2 requires Load context; AC4 adds M4 (architect finding, orchestrator decision, 2026-11-07)
- 2026-11-12 — implemented (developer): BANNED +math; AC1 test_schedules_leave_corpus_state_untouched; AC2 test_schedule_attribute_access_whole_module. F energies observed == tech note list.
- 2026-11-12 — AC4 mutants on throwaway copy (module path verified, copy deleted): M1 corpus.select() -> AC1+AC2 fail; M2 corpus.seen.add(-1) -> AC1+AC2 fail; M3 import math -> test_no_rng_or_clock_whole_module fails; M4 seed.times_selected += 1 -> AC1+AC2 fail (also test_fast_table x23 and test_uniform_constant_and_floor).
- 2026-11-12 — moved to review (developer); gates: mypy clean, pytest all pass, ruff clean on tests/test_schedule.py (repo-wide ruff has 1 RUF007 in tests/test_toy_parser.py, AFL-009's file, not touched)
- 2026-11-12 — review APPROVED (reviewer) -> testing. AC1: R/U/F full state (seeds, seen, _path_count, _seed_by_path, _pos) compared to R after every stream step; (i)-(iv) hold, (iii) recorded at call time; F energies recomputed == tech-note list. AC2: Load ctx, len()-only corpus.seeds, alias and method-call bans verified. AC3: BANNED == AC literal char for char, delta +math only. AC4: M1-M4 re-run on throwaway copy (module path verified, copy deleted), each fails the named tests; 19 extra mutants run, 16 caught. Escapes (outside AC wording, follow-up suggested): read-only getattr(corpus, "_pos"); setattr(corpus, "_extra", 1) (new attr, not in compared fields); getattr(corpus, "select")() gated on s > 100 (dynamic + unreached by stream). AC5: only tests/test_schedule.py changed for AFL-023, existing tests unchanged. Gates: ruff check tests/test_schedule.py clean, ruff check . clean (repo-wide), mypy src clean, pytest tests/test_schedule.py 30 passed; full pytest not run (AFL-009 sweep), tester to run it.
- 2026-11-12 — verified, ready to close (tester). Clean clone of HEAD b78f8c6 + working-tree tests/test_schedule.py only (module under test = clone src/fuzzer/schedule.py, printed in-test). Gates: ruff check . "All checks passed!"; mypy src "Success: no issues found in 8 source files"; pytest (default addopts, cov) "89 passed" x3, schedule.py 100% cov; tests/test_schedule.py 30 passed. One cold first run gave "1 failed, 88 passed": tests/test_executor.py::test_hang_stderr_is_bytes[echo hi >&2; exec sleep 5-hi\n] (stderr b"" vs b"hi\n" at timeout_s=0.3), timing flake in AFL-003's test, not AFL-023; passed 5/5 isolated and 3/3 full reruns; follow-up ticket suggested. AC4 mutants on clone copy: M1 corpus.select() -> AC1 ("fast diverged from R") + AC2 ("method call at 37"); M2 corpus.seen.add(-1) -> AC1 + AC2; M3 import math -> test_no_rng_or_clock_whole_module; M4 seed.times_selected += 1 -> AC1 + AC2 ("non-Load access at 38") (+23 test_fast_table, test_uniform_constant_and_floor); unmodified file passes all. AC3: BANNED == AC literal char for char (whitespace/trailing comma aside), 10 members, delta vs HEAD +math only. AC1 (i)-(iv) asserted in test and hold: len 12, 3 non-retained observes (path_freq 3, 2), F call at s=16 -> 2048 and s=17 -> 2048, energies include 16 (n=1) and 1 (n=12); F energies == tech-note list. AC5: clone differs from HEAD under src/ tests/ harness/ targets/ docs/ only in tests/test_schedule.py. Clone deleted.
- 2026-11-12 — DoD verified, moved to done (crew-lead)
