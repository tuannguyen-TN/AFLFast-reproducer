---
id: AFL-006
title: Power schedules — UNIFORM baseline + FAST (AFLFast)
requirement: FR-5
paper_ref: AFLFast §4.1 power schedules (FAST, eq. 4); AFLFast source afl-fuzz.c / config.h (AFL 2.51b base)
module: src/fuzzer/schedule.py
depends_on: [AFL-004]
status: done
owner: crew-lead
---

## Goal
Implement the project's independent variable: two energy functions, `uniform` and
`fast`, each `(seed, corpus) -> int`, registered in `SCHEDULES` (ADR-0004 §8);
`assign_energy` is only fuzzer.py's local alias for `SCHEDULES[cfg.schedule]`. UNIFORM reproduces vanilla-AFL equal energy; FAST implements
AFLFast's idea of more energy to seeds on low-frequency (rare) paths.

Energy spec decided (human, 2026-11-07), verified line by line against AFLFast's
primary source (github.com/mboehme/aflfast master, `afl-fuzz.c` / `config.h`;
AFLFast is based on AFL **2.51b**). All open questions are resolved; this ticket
now meets the Definition of Ready.

## Acceptance criteria
- [ ] **Formula exact.** schedule.py implements the spec in the technical notes
      exactly, using integer arithmetic only (no floats, no `math`), with a
      provenance comment (source file:line) on each constant.
- [ ] **Table test**, (s, f, `len(corpus.seeds)`) → `fast` energy:
      (0,1,any)→256; (1,100,1)→16; (1,100,10)→16; (1,100,11)→1; (3,5,any)→256;
      (4,2,any)→2048; (4,1,any)→4096; (15,1,any)→4096; (16,1,any)→4096;
      (16,33,1)→16; (16,33,11)→1; (10**6,7,any)→1024 (no overflow);
      (16,5,any)→1024 (pins next_p2 rounding: 32//8=4, not 32//5=6→1536);
      (15,33,any)→4096 (pins the s<16 boundary from below: s<15 would give 16 or 1).
      Plus `next_p2(1) == 1`, `next_p2(32) == 32`, `next_p2(33) == 64`.
- [ ] **Purity.** `dataclasses.asdict(seed)` and `corpus.seeds` are unchanged after
      each call (ADR-0004 §1, Consequences). An AST test over the whole module
      (inside functions too), modelled on `tests/test_mutator.py`'s
      sole-randomness test, bans RNG (`random`, `secrets`, `numpy.random`, `uuid`),
      `time` and `os.urandom` in schedule.py.
- [ ] **UNIFORM constant; both ≥ 1.** `uniform` returns 256 for every input,
      including seeds with varied fields and varied corpus size. Both schedules
      return an `int` ≥ 1.
- [ ] **Arm boundary (NFR-2).** `set(schedule.SCHEDULES) == {"uniform", "fast"}`.
      An AST test asserts that schedule.py imports only the standard library plus
      `fuzzer.corpus` (for the `Seed`/`Corpus` types). Together with the existing
      `test_corpus_does_not_import_schedule`, this makes the boundary between arms
      testable within this ticket. The remaining check, that fuzzer.py uses the
      arm name only for the `SCHEDULES` lookup, belongs to AFL-007's criteria.

## Technical notes (architect)
Interface fixed by ADR-0004 (`docs/adr/0004-corpus-schedule-contract.md`) §8:
```python
EnergyFn = Callable[[Seed, Corpus], int]
def uniform(seed: Seed, corpus: Corpus) -> int: ...
def fast(seed: Seed, corpus: Corpus) -> int: ...
SCHEDULES: dict[str, EnergyFn] = {"uniform": uniform, "fast": fast}
```
Pure function, no RNG, no side effects. schedule.py never writes `Seed` fields or
`corpus.seeds` and never calls a mutating `Corpus` method. f(i) ≥ 1 by
construction (ADR-0004 §2), so FAST needs no division guard.

**Spec (implement exactly; integer arithmetic only):**
```python
ALPHA = 256                # AFL config.h:79 HAVOC_CYCLES (base perf_score 100, afl-fuzz.c:4711)
BETA = 1                   # AFLFast config.h:92 POWER_BETA (code value; paper text says beta > 1)
MAX_FACTOR = 32 * BETA     # config.h:93
HAVOC_MAX_MULT = 16        # config.h:85 -> perf cap 1600 (afl-fuzz.c:4827) -> energy cap 4096
HAVOC_MIN = 16             # config.h:89; clamp at afl-fuzz.c:6170
SKIP_QUEUE_THRESHOLD = 10  # afl-fuzz.c:5160: abandon only if queued_paths > 10

def next_p2(n: int) -> int:   # afl-fuzz.c:4471-4480, smallest power of two >= n
    p = 1
    while p < n:
        p <<= 1
    return p

def uniform(seed, corpus) -> int:
    return ALPHA               # == AFLFast EXPLORE (factor 1); NOT EXPLOIT/"AFL" (factor MAX_FACTOR, saturates at 4096)

def fast(seed, corpus) -> int:
    s, f = seed.times_selected, seed.path_freq          # f >= 1 by ADR-0004
    factor = (1 << s) // f if s < 16 else MAX_FACTOR // next_p2(f)   # afl-fuzz.c:4803-4806
    factor = min(factor, MAX_FACTOR)                    # :4820-4821
    perf = min(100 * (factor // BETA), HAVOC_MAX_MULT * 100)   # :4823 divides first; :4827 cap
    if perf == 0:
        # AFLFast: queued_paths <= 10 -> stage_max 0 clamped to HAVOC_MIN;
        #          queued_paths > 10  -> abandon_entry (skip).
        # Deviation: we give 1 exec instead of skipping, so energy stays >= 1.
        return HAVOC_MIN if len(corpus.seeds) <= SKIP_QUEUE_THRESHOLD else 1
    return ALPHA * perf // 100                          # stage_max = HAVOC_CYCLES*perf/havoc_div/100 (:6154), havoc_div dropped
```

**Decision on α and energy inputs.** α ≡ `ALPHA` (256), a constant, in both arms.
AFL's per-seed `perf_score` adjustments (exec speed, bitmap size, handicap, depth;
`afl-fuzz.c:4717-4761`) are dropped in both arms, because they need edges (banned
as energy inputs by ADR-0004 §1), timing (breaks exec-index replay, NFR-1) or
depth (not tracked). FAST's energy reads only s(i) = `times_selected`,
f(i) = `path_freq` and `len(corpus.seeds)` (the corpus-size aggregate allowed by
ADR-0004 §1; amendment 2026-11-07). UNIFORM reads nothing. `exec_time`, `size`,
`edges` and `data` are not energy inputs.

**Floor.** Both schedules return an `int` ≥ 1 (ADR-0004 §8). UNIFORM is always
256. FAST's only zero-factor path returns `HAVOC_MIN` (16) or 1, and every
non-zero `perf` is ≥ 100, giving ≥ 256. The return of 1 instead of skipping
above 10 seeds is a deviation from AFLFast (disclosed in PRD §8), not AFLFast
behaviour.

## Test approach (tester)
`tests/test_schedule.py`: the (s, f, corpus size) → energy table and `next_p2`
cases above, using synthetic `Seed`s and corpora of the stated sizes; purity
(`asdict(seed)` and `corpus.seeds` compared before and after each call); the
whole-module AST ban on RNG/`time`/`os.urandom`; UNIFORM = 256 over varied seeds
and corpus sizes; `isinstance(e, int) and e >= 1` for both schedules. Later,
the campaign (AFL-011) checks the end-to-end effect.

## Log
- 2026-11-07 — created (req-engineer)
- 2026-11-07 — aligned with ADR-0004 (req-engineer)
- 2026-11-07 — recorded human decision: energy floor int ≥ 1 confirmed; AC now requires an explicit both-schedule test over extreme s(i), f(i), exec_time, size (req-engineer)
- 2026-11-07 — energy spec decided by human, verified against AFLFast source (architect). AC set replaced; α ≡ 256 in both arms, per-seed perf_score adjustments dropped; energy reads only (s, f, len(corpus.seeds)). Meets Definition of Ready; status stays backlog.
- 2026-11-07 — implemented schedule.py + tests/test_schedule.py (developer): formula/table/next_p2, purity, AST bans, uniform==256, SCHEDULES, import boundary all covered; ruff/mypy/pytest pass. Moved to review.
- 2026-11-07 — REVIEW: changes requested (bounce 1) (reviewer). Gates green (ruff, mypy, pytest 24/24 in test_schedule.py). Only schedule.py and test_schedule.py changed under src/tests (NFR-2 holds). Code matches the spec block exactly; all 12 table rows recomputed by hand and asserted. Mutation-tested a temp copy; three test gaps against the ACs:
  - **R1 Purity (AC "Purity"), blocking.** `before_seeds = list(corpus.seeds)` is a shallow copy holding the same Seed objects, so mutating a member in place (e.g. `corpus.seeds[0].path_freq += 1` inside fast) passes all tests (mutant survived). Snapshot `[dataclasses.asdict(x) for x in corpus.seeds]` (or a deepcopy) and compare after each call. Also check corpus.seeds purity for `uniform`, not only `fast`.
  - **R2 AST ban (AC "Purity", ban on os.urandom), blocking.** `from os import urandom as _u` passes `test_no_rng_or_clock_whole_module` (mutant survived): the alias hides the name, and the ImportFrom check compares "urandom" with "os.urandom". The model test in test_mutator.py bans import aliases. Either ban `asname` the same way or reject ImportFrom of `urandom` from `os`. Optional: also ban `__import__` / `importlib` names (`__import__('random')` also survived).
  - **R3 Formula pinning (AC "Formula exact"), required.** Replacing `MAX_FACTOR // next_p2(f)` with `MAX_FACTOR // f` survives, because the only s>=16 rows use f=7 and f=33, where 32//f == 32//next_p2(f). Add one s>=16 row with f in {3,5,6}, e.g. (16,5,any)->1024 (32//8=4; with no next_p2, 32//5=6 -> 1536). Also add (15,33,any)->4096 so the s<16 / s>=16 boundary is pinned from below (`s < 15` mutant survived; (15,1) cannot tell the branches apart).
  - Not findings: dropping `min(factor, MAX_FACTOR)` is an equivalent mutant with BETA=1 (the perf cap covers it), so no test can catch it; keep it for fidelity. Fixtures that set corpus.seeds directly are acceptable, because schedule reads only len(corpus.seeds) and Seed fields, and observe() would pull executor and filesystem into a pure-function unit. Default path_freq=0 raising ZeroDivisionError in fast(): acceptable as-is. ADR-0004 §2 guarantees f>=1 for every retained seed (test_corpus covers it), and a loud crash on a hand-built Seed is better than a silent guard that would change energy.
  Moved review -> in-progress.
- 2026-11-07 — bounce 1 fixes (developer), tests only: R1 deep asdict snapshot of corpus.seeds for uniform and fast; R2 AST ban rejects import aliases, os.urandom imports, __import__, importlib; R3 added rows (16,5,any)->1024 and (15,33,any)->4096. Each fix verified by mutation (path_freq write, 'from os import urandom as _u', MAX_FACTOR // f, s < 15). Back to review.
- 2026-11-07 — AC amended per review R3: table adds (16,5,any)→1024 and (15,33,any)→4096 (req-engineer)
- 2026-11-07 — RE-REVIEW: approved (reviewer). schedule.py is unchanged since review 1 (46+/9-), and only test_schedule.py was modified. Gates are green: ruff, mypy, and pytest 87 passed; schedule.py coverage is 100%. I re-ran 26 mutants against a temp copy outside the repo, which was deleted afterwards. All were killed except the documented equivalent mutant (dropping the factor cap is equivalent while BETA=1). R1 resolved: snap() takes asdict per member, and path_freq writes in fast and in uniform, times_selected writes, and appends are all caught. R2 resolved: the bans catch `from os import urandom as _u`, `from os import urandom`, `import os`, time, random alias, secrets, uuid, numpy.random, importlib, and `__import__('random')`. R2 is not over-broad: schedule.py uses no banned Name or Attribute (Seed fields and collections.abc.Callable are clean), and the real module passes. R3 resolved: the `MAX_FACTOR // f` and `s < 15` mutants are now killed. Every AC is met, including the amended table: (16,5,any)->1024 and (15,33,any)->4096 are asserted at n=1 and n=11. Moved review -> testing.
- 2026-11-07 — test: PASS, ready to close (tester). Clean clone of HEAD fe73240 plus exactly the two working-tree files src/fuzzer/schedule.py and tests/test_schedule.py (cmp-identical); pytest imports the clone's src (probe: <clone>/src/fuzzer/schedule.py). Gates in clone: ruff `All checks passed!`; mypy `Success: no issues found in 8 source files`; pytest `87 passed`, rc 0, schedule.py 100% coverage. ACs checked independently: all 14 table rows recomputed by hand and by a separate transcription of the spec block, which also matched fast() on a ~22k-point grid (s 0..39, 10^3, 10^6; f 1..69, 1023..1025, 10^9; corpus size 0/1/10/11/100); next_p2 1/32/33 -> 1/32/64; uniform == 256 everywhere; both return type int >= 1. Static AST check of schedule.py: no Div, no float constants, no math; attributes read only times_selected, path_freq, seeds; imports only collections.abc and fuzzer.corpus. Purity: asdict(seed), corpus.seeds, and the full Corpus state (seen, _path_count, _seed_by_path, _pos) are unchanged after every grid call. Determinism: repeat calls are equal, and the cross-process fingerprint is identical under PYTHONHASHSEED 0/1/12345. Arm isolation: SCHEDULES == {uniform, fast}; no other src/harness file references the arms (fuzzer.py and cli.py are stubs); importing fuzzer.corpus does not load fuzzer.schedule. Non-blocking test gaps (code is compliant today): a fast() that calls corpus.select() or writes corpus.seen, and `import math`, both survive the suite, because the purity test snapshots only corpus.seeds and the AC wording requires no more. Follow-up for req-engineer: PRD FR-5 says FAST energy increases with s(i), but the AFLFast-faithful branch switch is non-monotone at s 15->16 (f=3: 4096->2048, f=5: 4096->1024, f=33: 4096->16); amend FR-5 wording or disclose in PRD s8. Scratch clone deleted.
- 2026-11-07 — DoD verified, closed (crew-lead)
- 2026-11-07 — Goal wording aligned to ADR-0004 §8 / PRD FR-5 (req-engineer)
