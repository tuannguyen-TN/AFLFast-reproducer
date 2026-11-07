---
id: AFL-016
title: Third target — mini format parser with real branch structure + documented bugs (deep + shallow)
requirement: SC1, PRD §8 (Targets ≥3), NFR-6
paper_ref: AFLFast §2–3 (low-frequency paths get more energy; the schedule needs rare paths to find); Klees § performance measures / ground truth (known bugs as ground truth) and § benchmark choice
module: targets/mini_format.c (name proposed — confirm)
depends_on: [AFL-003]
status: backlog
owner: developer
---

## Goal
PRD §8 requires ≥3 targets: toy_parser, tlv_parser, "+ one more, e.g. a mini format
parser". This ticket adds that third target. It exists to give the power schedule
something to tell apart. FAST's advantage (AFLFast) comes from putting energy on
low-frequency paths. A target with only a few paths, or with a bug reachable by one
byte check (tlv-1, see the AFL-010 methodology flag), cannot show that advantage.
So the ACs below require **real, measurable branch structure** and a **deep planted
bug (`mfp-1`) behind a multi-step path**. Each step is a separate coverage edge, and
no single mutation of the seed reaches that bug. Per PRD §8 (changed 2026-11-07,
human decision: ≥2 planted bugs per target) a second, **shallow** bug (`mfp-2`) is
added so unique-crash counts (PRD §8(b)) have range. Both bugs are ground truth for
SC1 and for time-to-first-crash per planted bug (PRD §8(c)).

**Why `depends_on: [AFL-003]`.** Several ACs are checked through `Executor`
(`outcome`, `edges`) and `coverage.path_id`. AFL-003 is done, so this ticket is
unblocked. The dependency is listed so that the verification tool is traceable.
AFL-009/010 now also depend on AFL-003 (human decision, 2026-11-07), since their
depth ACs are measured through `Executor` as well.

### Why these numbers
- **≥4 record types + a reject/default branch.** This gives at least 5 dispatch
  edges from one branch point. That is the smallest number at which a corpus has
  clearly frequent and clearly rare dispatch arms. It stays small enough for one
  file.
- **≥20 distinct `path_id`s from hand-written benign inputs.** This matches the
  AFL-011 pilot floor ("median `distinct_path_ids` < 20" triggers the granularity
  fallback). The target must be able to exceed that floor by construction. If it
  cannot, a pilot trigger on this target would measure the target's poverty, not
  the coverage granularity. 20 is a floor that hand-written inputs can show. A
  fuzzing run is expected to reach many more.
- **≥3 edge-visible steps to the bug, ≥1 of them cross-record.** toy-1 needs 3
  byte compares in one position chain. tlv-1 needs 1 step. Three steps, one of
  which depends on state set by an earlier record, put the bug clearly deeper than
  both existing targets without making it unreachable in a 600 s budget. Each step
  being its own edge means presence-only coverage (ADR-0001) retains every
  intermediate input, so a gradient leads to the bug.
- **No single-byte substitution of the seed crashes at `mfp-1`'s site.** This is the
  objective form of "not reachable by a single byte check". It is exactly the
  property tlv-1 lacks. It is scoped to `mfp-1`'s site because `mfp-2` is shallow by
  design and *will* be one substitution away.

### Depth definitions (shared with AFL-009 / AFL-010)
Both are measured against the target's shipped seed `S0` through `Executor`. A crash
is **at bug X's site** iff, in its ASan report, the first stack frame located in
the target's own source file names X's documented function (frames inside ASan
interceptors such as `__asan_memcpy` are skipped). ADR-0002 forces `symbolize=1`, so
frames are named.
- **Shallow:** at least one single-byte substitution of `S0` (some position, some
  value) crashes at the bug's site.
- **Deep:** no single-byte substitution of `S0` crashes at the bug's site, **and** a
  documented staircase `S0 → … → Sk` with k ≥ 3 reaches it, each step clean and
  adding ≥1 new edge.

Why this definition rather than "≤ 1–2 edge-visible steps": it is binary,
needs no judgement about which edges "count", and uses one tool for both verdicts.
The same ≤ 256 × |S0| sweep proves `mfp-2` shallow and `mfp-1` not shallow. It also
matches what separates the arms. A bug one substitution from a seed is found by
both arms within seconds (the tlv-1 problem), while a bug that needs several
retained intermediate inputs is where energy allocation can matter (AFLFast §2–3).

## Acceptance criteria
- [ ] **Build.** `make -C targets` builds `targets/bin/<name>` through the existing
      pattern rule, so it gets `REQUIRED_FLAGS` (`-O0`, ASan, trace-pc-guard) and
      links `cov_rt.c`. The only Makefile change is adding the binary to `TARGETS`.
      No per-target flags.
- [ ] **Scope.** One C source file. It reads input only from stdin and does no
      network I/O and no file I/O beyond stdin (NFR-6). Each run's work is bounded
      by the input length: every loop's trip count is bounded by the number of
      input bytes or by a constant.
- [ ] **Format structure (documented in the header comment).** The format has:
      (a) a fixed header with a magic value of ≥2 bytes plus ≥1 header field that
      changes later parsing (e.g. version or flags);
      (b) a **sequence** of ≥1 records parsed in a loop until the input ends;
      (c) **≥4 record types** dispatched on an input byte value, plus a distinct
      reject/default branch for unknown types;
      (d) **nesting:** ≥1 record type contains sub-fields whose count or layout is
      set by a value inside that record;
      (e) **cross-record state:** ≥1 check depends on a value set by an earlier
      record or by the header.
- [ ] **Path diversity (measured).** The source or a test file documents a set of
      ≥20 hand-written benign inputs. Run through `Executor` (default timeout), every
      one has `outcome == "clean"`, and their `coverage.path_id(r.edges)` values are
      pairwise distinct (≥20 distinct `path_id`s). The set includes the empty input,
      a magic-only input, a truncated record, and an unknown record type.
- [ ] **Planted bugs (changed 2026-11-07, human decision: ≥2 per target).** Exactly
      two planted bugs, ids `mfp-1` (deep) and `mfp-2` (shallow). Each is an
      ASan-detectable memory-safety error (out-of-bounds read or write) at a
      **single crash site** in its own function. The two functions differ, and
      neither contains any other crash site, so AFL-013 maps each bug to its own
      bucket and ground-truth entry. The source comment for each documents its id,
      function, trigger condition, expected ASan report type and depth class
      (shallow/deep as defined above).
- [ ] **Depth of `mfp-1`: staircase inputs (measured).** The source documents a chain of inputs
      `S0 → S1 → … → Sk` with **k ≥ 3**. `S0` is the shipped valid seed (below) and
      `Sk` is the trigger. For every i < k, `Si` has `outcome == "clean"`, and
      `edges(S(i+1)) − edges(Si)` is non-empty (each step reaches ≥1 new edge, so
      presence-only coverage would retain it). **≥1 step is cross-record:** it
      passes only because of a value set in an earlier record or the header (AC (e)).
- [ ] **Trigger (`mfp-1`).** `Sk`, run through `Executor`, gives `outcome == "crash"`,
      `signal == SIGABRT` and `stderr` containing `ERROR: AddressSanitizer:` with
      the documented report type, under ADR-0002's forced `ASAN_OPTIONS`. The crash
      is at `mfp-1`'s site (definition above).
- [ ] **Trigger (`mfp-2`).** The source documents a trigger input `T2` for `mfp-2`
      that differs from `S0` by exactly one byte substitution. Run through
      `Executor`, it gives `outcome == "crash"`, `signal == SIGABRT`, `stderr`
      containing `ERROR: AddressSanitizer:` with `mfp-2`'s documented report type,
      and the crash is at `mfp-2`'s site. (This is the shallow-depth proof.)
- [ ] **`mfp-1` is not one mutation away (measured).** For the shipped seed `S0`
      (≤ 32 bytes), run every single-byte substitution (every position × all 256
      values, ≤ 8192 execs) through `Executor`. No result is a crash at `mfp-1`'s
      site. Crashes at `mfp-2`'s site are expected and allowed. The test may be
      marked slow.
- [ ] **No other crashes or hangs.** Every documented benign and staircase input
      (`S0..S(k-1)`) has `outcome == "clean"` and exit status 0. None gives `"hang"`.
      In the single-byte sweep above, every crash is at the site of `mfp-1` or
      `mfp-2` (none at an undocumented site), and no result is `"hang"`.
- [ ] **Seed.** A valid seed input `S0` (≤ 32 bytes, `outcome == "clean"`) is
      committed at `targets/seeds/<name>/S0`, where `<name>` is this target's
      binary name (`targets/bin/<name>`; currently `mini_format`, so
      `targets/seeds/mini_format/S0`, and the directory follows any rename under
      OQ 4). It is the only file in that directory and this target's sole initial
      corpus (AFL-011), and it is the same file the single-byte sweep, the `mfp-2`
      trigger and the `mfp-1` staircase above are measured against.
- [ ] **Ground truth.** `mfp-1` and `mfp-2` are each recorded with `target`,
      `function` and `file` in the same ground-truth mechanism AFL-009/010 adopt
      (proposed `targets/ground_truth.json`), so per-bug time-to-first-crash (PRD
      §8(c)) is computable by AFL-013. The two entries name different functions.
- [ ] **Retuning and freeze.** `mfp-1` (deep) is governed by AFL-011's AC
      "Pre-registered target retuning rule and freeze", which is the canonical
      text. Any retune of this target, with its triggering first-pilot numbers,
      and the freeze commit hash are recorded in this ticket's Log.

## Open questions (resolve before leaving backlog)
1. **Bug class.** Should `mfp-1` be a different ASan class from tlv-1
   (stack-buffer-overflow), e.g. a heap-buffer-overflow read, so the three targets'
   bugs are distinguishable by report type as well as by site? Proposed default:
   yes. The ACs do not require it.
2. ~~**One bug or more?** With one planted bug per target, the "unique crashes"
   variable (PRD §8(b)) is 0 or 1 per trial on every target. That is the same issue
   AFL-009 raises. Should this target add a second, shallower bug (e.g. reachable
   from a single record) so unique-crash counts have range? Not added here, to keep
   scope tight. Needs a Vision/PRD decision.~~
   **Resolved (human, 2026-11-07).** PRD §8 now requires ≥2 planted bugs per
   target. `mfp-2` (shallow) is added; see the Planted bugs and Trigger (`mfp-2`) ACs.
3. ~~**Discrimination is not proven by this ticket.** The ACs prove structure and
   depth. They do not prove the bug is *rare under UNIFORM* in practice, because
   the fuzzer (AFL-007) does not exist yet. The empirical check is the AFL-011
   pilot. Proposed rule, to pre-register before the pilot runs: if the pilot shows
   that neither arm ever finds `mfp-1`, or both find it in every trial within
   the first 5 % of the budget, the target may be retuned **once**, before the
   main campaign, with the change logged here. After that the target is frozen at
   a recorded commit (NFR-1, no post-hoc tuning). Needs a crew-lead/Vision decision.~~
   **Resolved (human, 2026-11-07).** The rule is adopted. Its canonical text is
   AFL-011's AC "Pre-registered target retuning rule and freeze", and this
   ticket's "Retuning and freeze" AC points to it.
6. ~~**Re-pilot after a retune?** The adopted rule does not say whether the pilot is
   re-run after a one-time retune to record the retuned target's numbers. It also
   does not order the retune relative to AFL-011's granularity fallback, which
   also re-runs the pilot. Proposed default: apply both decisions from the same
   first pilot, then run one confirmation pilot, which is recorded and not
   re-evaluated. Needs a crew-lead decision.~~
   **Resolved (human, 2026-11-07).** Both pilot rules are evaluated once, on the
   first pilot only, and each fires at most once. After any changes, one
   confirmation pilot runs. It is recorded and reported but never re-evaluates or
   re-triggers either rule. Then the targets and config are frozen. See AFL-011.
7. ~~**Retune for the other deep bugs?** (raised in AFL-009/010: should the rule also
   cover `toy-1` and `tlv-2`?)~~
   **Resolved (human, 2026-11-07).** Yes. The rule covers every deep bug (`toy-1`,
   `tlv-2`, `mfp-1`) with the same thresholds, and each target is retuned at most
   once. See AFL-011.
4. **Name.** `mini_format.c` is a placeholder. The architect may rename it.
   Downstream configs follow the name.
5. **Size cap.** Should there be a hard line cap (e.g. ≤ 250 non-comment lines) to
   guard scope (NG4, `vision.md`)? Not made an AC, because the structural ACs
   already bound the work.

## Technical notes (architect)
<to be filled by architect — format layout, record types, bug placement, and how it
fits ADR-0001/0002. Do not design the parser here.>

## Test approach (tester)
All measured ACs go through `Executor` + `coverage.path_id`. That covers path
diversity (≥20 distinct ids, all clean), the staircase (clean prefix steps with
strictly new edges, crashing final step), the trigger classification for both
bugs (SIGABRT, ASan report, crash site by first in-source ASan frame), and the
single-byte-substitution sweep over `S0` (slow-marked). The sweep must show no
`mfp-1`-site crash, only `mfp-1`/`mfp-2` sites, and no hangs.
Grep and review checks cover stdin-only I/O, the single crash site, and the
ground-truth entry. End-to-end discovery by the fuzzer is verified under
AFL-007/AFL-011, not here.

## Log
- 2026-11-07 — created (req-engineer)
- 2026-11-07 — per human decisions: added shallow bug `mfp-2` (PRD §8 now needs ≥2
  bugs per target). Scoped the not-one-mutation-away AC to `mfp-1`'s site. Defined
  shallow/deep and "at a bug's site". Adopted the retuning rule as an AC with a
  freeze point. Resolved OQ 2 and 3, added OQ 6 (req-engineer)
- 2026-11-07 — per human decisions: the retuning rule moves to AFL-011 as the
  canonical AC covering all deep bugs, and this ticket keeps a pointer AC. Resolved
  OQ 6 (one evaluation on the first pilot, then one confirmation pilot that never
  re-triggers). Recorded and resolved OQ 7 (rule covers toy-1 and tlv-2)
  (req-engineer)
- 2026-11-07 — per human decision: Seed AC pins `S0` at
  `targets/seeds/<name>/S0` (binary name, currently `mini_format`), the sole
  initial corpus and the file all depth measurements use (req-engineer)
