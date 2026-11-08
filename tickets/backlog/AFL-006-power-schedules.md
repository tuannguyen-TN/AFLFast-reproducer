---
id: AFL-006
title: Power schedules — UNIFORM baseline + FAST (AFLFast)
requirement: FR-5
paper_ref: AFLFast §4.1 power schedules (FAST, eq. 4); AFLFast source afl-fuzz.c / config.h (AFL 2.51b base)
module: src/fuzzer/schedule.py
depends_on: [AFL-004]
status: backlog
owner: developer
---

## Goal
Implement the project's independent variable: `assign_energy(seed, corpus) -> int`
with two schedules. UNIFORM reproduces vanilla-AFL equal energy; FAST implements
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
      (16,33,1)→16; (16,33,11)→1; (10**6,7,any)→1024 (no overflow).
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
