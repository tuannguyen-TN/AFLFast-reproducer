# ADR-0004: Corpus ↔ schedule contract (seed metadata, f(i), s(i), selection, energy interface)

- **Status:** accepted (human decisions, 2026-11-07)
- **Date:** 2026-11-07
- **Owner:** architect
- **Related:** AFL-004, AFL-006, AFL-007, AFL-008, AFL-011, AFL-009/010/016 (S0), FR-3, FR-5, NFR-1, NFR-2, PRD §8
- **Numbering:** ADR-0003 is reserved by AFL-013 (crash dedup), ADR-0005 by AFL-007 (stopping and reproducibility).

## Context
AFLFast's power schedule is a function of two per-seed quantities: s(i), the number
of times seed t_i has been chosen from the queue, and f(i), the number of generated
inputs that exercise path i (AFLFast §4.1; FAST is eq. 4,
p(i) = min(α(i)/β · 2^s(i)/f(i), M)). The corpus (AFL-004) owns both counters.
The schedule (AFL-006) only reads them. The loop (AFL-007) drives both. If any of
the three defines a counter differently, FAST computes the wrong thing, or the
arms differ somewhere other than schedule.py and NFR-2 breaks. This ADR is the
single contract all three build against.

CLAUDE.md §2 governs this contract. Coverage decides only (a) retention and
(b) energy, through the schedule. AFLFast changes only (b) in this project.

## Options considered
1. **One contract ADR** covering metadata, f(i), s(i), selection and the energy
   interface. Pro: these pieces depend on each other (for example, f(i) ≥ 1 is
   what makes FAST's division safe). Con: a longer ADR.
2. **Split** into a metadata/f(i) ADR and a schedule-interface ADR. Con: the
   coupling above crosses the split, so either ADR could change without the other.
   Rejected by human decision.

## Decision
**Option 1.** The contract has eight parts.

### 1. Seed record (corpus.py); schedule.py treats it as read-only
```python
@dataclass
class Seed:
    id: int                 # insertion index, 0-based; also the queue file name
    data: bytes
    edges: frozenset[int]   # from the retaining run; never empty (see 2)
    path_id: int            # coverage.path_id(edges)
    exec_time: float        # ExecResult.exec_time of the retaining run (see 7)
    times_selected: int = 0 # s(i)
    path_freq: int = 0      # f(i); ≥ 1 once the seed is in the corpus
    @property
    def size(self) -> int: return len(self.data)
```
schedule.py may read every field of `Seed` and `corpus.seeds`. It never assigns
to them, appends, reorders or calls a mutating `Corpus` method. Only `corpus.py`
writes `times_selected` and `path_freq`. Energy may use `times_selected`,
`path_freq`, `exec_time`, `size`, and aggregates of these over `corpus.seeds`.
`edges` and `data` are visible but are not energy inputs: the scheduler stays
blind to raw coverage (AFL-006).

### 2. f(i): clean executions on the seed's path
- **Definition.** f(i) is the number of executions with `outcome == "clean"` whose
  `path_id` (over the presence edge set, ADR-0001) equals `seed.path_id`. Both
  retained and discarded runs count. This is the analogue of AFLFast's `n_fuzz`
  map {(cksum(i), f(i))}: AFLFast tracks f(i) via a per-path map counting the
  number of generated (and potentially discarded) inputs exercising each path
  (AFLFast §5.1). The map's key is
  `coverage.path_id`, the only path identity in the package. If the pre-registered
  hit-count pilot (ADR-0001) switches features, this definition holds over the
  new feature set.
- **Storage.** The corpus keeps `_path_count: dict[int, int]` over every clean
  path it observes, and `_seed_by_path: dict[int, Seed]`, so it can update the
  owning seed's `path_freq` in O(1). `Seed.path_freq` is a mirror of
  `_path_count[seed.path_id]` and is always equal to it.
- **Seeds and paths are 1:1.** A retained input has ≥1 edge that no earlier
  input had, so its edge set differs from every earlier seed's edge set, and so
  does its `path_id` (barring a 64-bit blake2b collision). Also, `seen` only
  grows. So if a path is not retained the first time it occurs, it can never be
  retained later. A seed's retaining run is therefore the first occurrence of its
  path. f(i) = 1 at retention and f(i) ≥ 1 afterwards, so FAST never divides by
  zero. The schedule never reads counts for paths that have no seed.
- **`observe()` order.** (1) Raise `ValueError` unless `result.outcome == "clean"`.
  (2) Compute `pid = coverage.path_id(result.edges)`, increment `_path_count[pid]`,
  and if `pid in _seed_by_path`, set that seed's `path_freq`. (3) If
  `coverage.has_new_edges(result.edges, seen)`, add the edges to `seen`, then
  create, persist and append a `Seed` with `path_freq = _path_count[pid]` (= 1)
  and return it. Otherwise return `None`.
- **Excluding crashes and hangs is part of the definition, not an
  approximation.** f(i) is consulted only for retained seeds. A seed is retained
  only from a clean run, because `observe()` refuses anything else and AFL-007
  sends crashes to crash storage and hangs to the `hangs` counter (this matches
  AFLFast Algorithm 1, lines 11–14: a crashing t′ goes to T✗, never to T). The
  question is whether a non-clean run can carry a seed's `path_id`. If it cannot,
  excluding it changes nothing.
  - *Hang.* The executor returns `edges = frozenset()` on timeout. Every seed's
    edge set is non-empty, because retention needs ≥1 new edge. So a hang can
    never match a seed's path. Its true path is unobservable, because the
    executor discards the bitmap. That is a measurement limit, and it applies
    equally to both arms.
  - *Crash.* A crashing run's bitmap holds the blocks entered before the fault.
    The trace-pc-guard guard fires on block entry, and the ASan runtime is not
    coverage-instrumented. For this set to equal a clean run's set, the crashing
    run must have entered every block of the clean path before faulting,
    including the clean path's *final* block, the one whose return or `exit()`
    ends the process. In the normal case the crashing run stops before reaching
    that final block. Its edge set is then a different, truncated path, and its
    `path_id` belongs to no seed.
  - **Residual case, stated honestly.** The exception is a fault *inside or
    beneath* the clean path's final block: the block was entered (guard fired),
    then a call made from it, before the process exits, faults in code that the
    clean run also covers in full. Example: a value-triggered overflow in the
    last callee before `return`. That crashing run has exactly the seed's
    `path_id`, and an all-outcome count like `n_fuzz` would include it. Ours does
    not, by definition. The difference is at most the number of crashes on that
    path. Those crashes are saved and counted as crashes. Under FAST, f(i) for
    such a path is lower than an all-outcome count, so the path gets slightly
    more energy. The rule is the same in both arms, and UNIFORM does not read
    f(i), so this does not leak a difference between arms. It is a definitional
    difference from AFLFast and must be disclosed as one, not hidden.

### 3. s(i): times selected
`times_selected` changes only in `mark_fuzzed(seed)` (`+= 1`). The loop calls it
after the seed's whole energy has been spent. So the first `assign_energy` call
for a seed sees s(i) = 0. This matches AFLFast, where s(i) is the number of times
the seed t_i has previously been chosen from the queue (§4.1). If the time
budget expires partway through a seed's energy, the run ends. Whether that last `mark_fuzzed` happens makes no
observable difference.

### 4. Selection: fixed round-robin in corpus.py, identical in both arms
`select()` returns seeds in insertion order and cycles back to the start, with no
RNG and no reads of s(i), f(i) or energy. It raises on an empty corpus. Its exact
form, which avoids the counter-modulo trap:
```python
def select(self) -> Seed:
    if not self.seeds: raise RuntimeError("select() on empty corpus")
    i = self._pos % len(self.seeds)   # length read now: seeds retained mid-cycle join it
    self._pos = i + 1
    return self.seeds[i]
```
Seeds appended during a cycle are reached before the cycle wraps, as in AFL's
queue. Do **not** keep a monotonically growing counter and take
`counter % len`. When the length changes, that scheme re-selects or skips seeds.
Selection is in corpus.py, which has no schedule import or parameter.
schedule.py affects **only** energy (CLAUDE.md §2). The *rule* is identical in
both arms. The *sequence* of seeds differs once the arms retain different inputs,
and that difference is a downstream effect of energy.

### 5. Deviation from AFLFast as published (self-contained; mirror into PRD threats to validity)
> AFLFast is two changes to AFL: a power schedule (`assignEnergy`, AFLFast §4.1)
> and a search strategy (`chooseNext`, §4.2–4.3). The search strategy prioritises
> seeds with low s(i) and low f(i), both when designating "favourites" (Strategy 1)
> and when choosing the next favourite from the queue (Strategy 2). This project
> reproduces the power schedule in isolation. Both arms choose seeds by the same
> fixed round-robin in insertion order. Both arms also omit AFL's favoured-seed
> culling (`top_rated` / `cull_queue`; AFLFast §2.1 notes that AFL's `chooseNext`
> "mostly ignores non-favorite seeds") and AFL's probabilistic skipping of
> non-favoured or already-fuzzed seeds. Per §5.4 / Fig. 11, the paper's
> 'No Strategy' configuration — AFLFast with the exponential power schedule but
> neither search strategy, which the authors describe as comparable to AFL but
> with an exponential power schedule — is the power-schedule-in-isolation arm
> this project reproduces. At 24h, AFLFast with both strategies exposes almost
> twice as many unique crashes as AFLFast with no strategy; equivalently,
> 'No Strategy' reaches roughly half the unique crashes of full AFLFast.
> Consequences: (i) our results bear on the power schedule alone, not on AFLFast
> as published, and a null or small effect does not refute the full AFLFast
> result; (ii) the UNIFORM baseline is a constant-energy schedule on a plain
> round-robin queue, so it does not replicate vanilla AFL's queue behaviour
> byte for byte; (iii) we seed every trial with the target's S0 (§6 below),
> whereas AFLFast's experiments used a single seed, the empty file (§5.1). The
> isolation is deliberate (NFR-2: the schedule is the only independent
> variable), and it applies identically to both arms.

### 6. Initial seeds
The initial corpus is exactly the target's shipped seed file
`targets/seeds/<target>/S0`. This is the same file that PRD §8 bug-depth
(shallow/deep) definitions are measured against. The corpus does not choose
seeds, and there is **no `b""` fallback**. A missing S0 is an error. Loading S0
and running it belongs to AFL-007/008/011. The loop executes S0 and passes the
result to `observe()` under the same rule as any other input. Because `seen`
starts empty, S0 is retained if its run is clean with ≥1 edge, and it becomes
seed 0 with f = 1. If S0 is clean with zero edges, `has_new_edges` is false, the
corpus stays empty, and `select()` raises. AFL-007's "no instrumentation
detected" startup guard must fire before that happens. If S0 crashes or hangs,
`observe()` raises. That is correct, because S0 must be clean (AFL-009/010/016).

### 7. exec_time and persistence
`exec_time` is the `ExecResult.exec_time` of the single run that retained the
seed. There is no averaging and no re-run. On retention the corpus writes the raw
bytes to `<out>/queue/id_<id:06d>` and creates the directory on the first write.
Persistence is write-only, with no reload and no resume.

### 8. Schedule interface (schedule.py)
```python
EnergyFn = Callable[[Seed, Corpus], int]

def uniform(seed: Seed, corpus: Corpus) -> int: ...
def fast(seed: Seed, corpus: Corpus) -> int: ...

SCHEDULES: dict[str, EnergyFn] = {"uniform": uniform, "fast": fast}
```
- Each schedule is a pure function. It reads only what §1 allows, has no RNG and
  no side effects, and returns an `int ≥ 1`. The fuzzer may assert this.
- fuzzer.py's only use of the arm name is
  `assign_energy = schedule.SCHEDULES[cfg.schedule]`. An unknown name raises
  `KeyError`. cli.py (AFL-008) takes its `--schedule` choices from
  `SCHEDULES.keys()`.
- **Left open for AFL-006 (not decided here):** UNIFORM's constant; FAST's α(i),
  β and M; how FAST rounds its result and clamps it to ≥1; and whether α(i) uses
  `exec_time` or `size`. This ADR fixes only the shape and the meanings of s(i)
  and f(i). **Resolved 2026-11-07 in AFL-006; see the amendment at the end.**

## Consequences
- NFR-2 holds by structure. corpus.py, the only owner of retention, f(i), s(i)
  and selection, never imports schedule.py or receives the arm name. The arms
  differ only inside the function looked up in `SCHEDULES`.
- NFR-1: the corpus uses no RNG, and no decision iterates a set or depends on
  dict order (the dicts are lookup-only).
- FAST's division is safe without a guard, because f(i) ≥ 1 by construction (§2).
- Tests. AFL-004: f increments on discarded clean runs that share a seed's path;
  f = 1 at retention; `observe()` raises on crash and hang results; `select()`
  wraps and picks up mid-cycle appends; `select()` raises when the corpus is
  empty. AFL-006: `assign_energy` leaves `dataclasses.asdict(seed)` and
  `corpus.seeds` unchanged.
- Disclosure: §5 (search strategy, culling and skipping omitted; S0 rather than
  the empty seed) and the §2 residual case go into the report's threats to
  validity.
- Memory: `_path_count` grows with the number of distinct clean paths. This is
  acceptable at our scale.

## Amendment (2026-11-07): §8 open items resolved by AFL-006
The items §8 left open were decided by the human and checked line by line
against AFLFast's source (github.com/mboehme/aflfast master, `afl-fuzz.c` /
`config.h`, based on AFL 2.51b). The full spec and its provenance comments are in
`tickets/done/AFL-006-power-schedules.md`. In summary: α ≡ 256 (AFL's
`HAVOC_CYCLES` at base `perf_score` 100) in both arms. AFL's per-seed
`perf_score` adjustments (exec speed, bitmap size, handicap, depth) are dropped
in both arms, so neither `exec_time` nor `size` is used. UNIFORM returns 256 for
every seed, which matches AFLFast's EXPLORE schedule. FAST follows AFLFast's
integer code: factor = 2^s(i) / f(i) for s(i) < 16, else 32 / next_p2(f(i)),
capped at M = 32; β = 1 (`POWER_BETA`); perf capped at 1600, so energy is capped
at 4096; energy = 256 · perf / 100. The s(i) ≥ 16 branch is independent of
s(i), so energy is non-monotone in s(i): it drops at s(i) 15→16 for
3 ≤ f(i) ≤ 32768 (PRD §8 (viii)). A zero-factor seed gets `HAVOC_MIN` (16)
execs while the corpus holds ≤ 10 seeds and 1 exec above that, where AFLFast
skips the seed instead. So both schedules still return an `int` ≥ 1 as §8
requires. FAST reads only `times_selected`, `path_freq` and `len(corpus.seeds)`.
UNIFORM reads nothing.

On §1: `len(corpus.seeds)` is a count over `corpus.seeds`, which schedule.py may
read, so it is an aggregate over `corpus.seeds` and is allowed under §1. This
amendment makes that explicit. It also narrows §1 for this project's schedules:
`exec_time` and `size` remain readable but are not energy inputs. §1–§8 above are
otherwise unchanged.

## Amendment (2026-11-07): consistency with PRD FR-5
Editorial only, for consistency with the reworded PRD FR-5 and PRD §8 (viii). The
amendment above now points to the AFL-006 ticket's current path
(`tickets/done/`) and states the energy drop at s(i) 15→16. No formula or
decision changed.
