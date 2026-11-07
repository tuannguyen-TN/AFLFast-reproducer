---
id: AFL-006
title: Power schedules — UNIFORM baseline + FAST (AFLFast)
requirement: FR-5
paper_ref: AFLFast § power schedules / exponential schedule
module: src/fuzzer/schedule.py
depends_on: [AFL-004]
status: backlog
owner: developer
---

## Goal
Implement the project's independent variable: `assign_energy(seed, corpus) -> int`
with two schedules. UNIFORM reproduces vanilla-AFL equal energy; FAST implements
AFLFast's idea of more energy to seeds on low-frequency (rare) paths.

## Acceptance criteria
- [ ] `UNIFORM` returns a constant energy regardless of seed.
- [ ] `FAST` increases energy with the seed's selection count and decreases it with
      the frequency of the path it exercises (exponential form per AFLFast).
- [ ] Schedule is selected by a single parameter; **no other module** changes
      behaviour between arms (NFR-2).
- [ ] Unit tests: UNIFORM equal across seeds; FAST gives strictly more energy to a
      rare-path seed than to a high-frequency one.
- [ ] Every schedule returns an `int ≥ 1` for every seed, so the loop never gets
      zero energy (ADR-0004 §8; ≥1 rule confirmed (human, 2026-11-07; ADR-0004 §8)).
      Test (explicit, both `uniform` and `fast`): over synthetic corpus states, assert
      `isinstance(e, int) and e >= 1` for each of: s(i)=0 and very large s(i) (e.g.
      10**6); f(i)=1 and very large f(i) (e.g. 10**9), so a raw FAST value that
      tends toward 0 is clamped to 1; extreme `exec_time` (tiny and huge) and `size`
      (0-byte and very large); a single-seed corpus; and combinations of these
      extremes in one state.
- [ ] Purity: `assign_energy` leaves `dataclasses.asdict(seed)` and
      `corpus.seeds` unchanged (ADR-0004 §1, Consequences).

## Technical notes (architect)
Interface fixed by ADR-0004 (`docs/adr/0004-corpus-schedule-contract.md`) §8:
```python
EnergyFn = Callable[[Seed, Corpus], int]
def uniform(seed: Seed, corpus: Corpus) -> int: ...
def fast(seed: Seed, corpus: Corpus) -> int: ...
SCHEDULES: dict[str, EnergyFn] = {"uniform": uniform, "fast": fast}
```
Pure function, no RNG, no side effects. Readable fields (ADR-0004 §1): schedule.py
may read every `Seed` field and `corpus.seeds`, but never writes them or calls a
mutating `Corpus` method. Energy inputs are limited to `times_selected` (s(i)),
`path_freq` (f(i)), `exec_time`, `size`, and aggregates of these over
`corpus.seeds`. `edges` and `data` are visible but must not be energy inputs, and
the schedule never reads coverage bitmaps: it stays blind to raw coverage beyond
f(i). f(i) ≥ 1 by construction (ADR-0004 §2), so FAST needs no division guard.
Left to this ticket (ADR-0004 §8): UNIFORM's constant; FAST's α(i), β and M; how
FAST rounds and clamps to ≥1; whether α(i) uses `exec_time` or `size`.

## Test approach (tester)
`tests/test_schedule.py`; construct synthetic corpus states and assert energy
ordering. Later, campaign (AFL-011) checks the end-to-end effect.

## Log
- 2026-11-07 — created (req-engineer)
- 2026-11-07 — aligned with ADR-0004 (req-engineer)
- 2026-11-07 — recorded human decision: energy floor int ≥ 1 confirmed; AC now requires an explicit both-schedule test over extreme s(i), f(i), exec_time, size (req-engineer)
