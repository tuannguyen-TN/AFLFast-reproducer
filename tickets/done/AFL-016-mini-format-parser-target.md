---
id: AFL-016
title: Third target — mini format parser with real branch structure + documented bugs (deep + shallow)
requirement: SC1, PRD §8 (Targets ≥3), NFR-6
paper_ref: AFLFast §2–3 (low-frequency paths get more energy; the schedule needs rare paths to find); Klees § performance measures / ground truth (known bugs as ground truth) and § benchmark choice
module: targets/mini_format.c (name proposed — confirm)
depends_on: [AFL-003]
status: done
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
- [x] **Build.** `make -C targets` builds `targets/bin/<name>` through the existing
      pattern rule, so it gets `REQUIRED_FLAGS` (`-O0`, ASan, trace-pc-guard) and
      links `cov_rt.c`. The only Makefile change is adding the binary to `TARGETS`.
      No per-target flags.
- [x] **Scope.** One C source file. It reads input only from stdin and does no
      network I/O and no file I/O beyond stdin (NFR-6). Each run's work is bounded
      by the input length: every loop's trip count is bounded by the number of
      input bytes or by a constant.
- [x] **Format structure (documented in the header comment).** The format has:
      (a) a fixed header with a magic value of ≥2 bytes plus ≥1 header field that
      changes later parsing (e.g. version or flags);
      (b) a **sequence** of ≥1 records parsed in a loop until the input ends;
      (c) **≥4 record types** dispatched on an input byte value, plus a distinct
      reject/default branch for unknown types;
      (d) **nesting:** ≥1 record type contains sub-fields whose count or layout is
      set by a value inside that record;
      (e) **cross-record state:** ≥1 check depends on a value set by an earlier
      record or by the header.
- [x] **Path diversity (measured).** The source or a test file documents a set of
      ≥20 hand-written benign inputs. Run through `Executor` (default timeout), every
      one has `outcome == "clean"`, and their `coverage.path_id(r.edges)` values are
      pairwise distinct (≥20 distinct `path_id`s). The set includes the empty input,
      a magic-only input, a truncated record, and an unknown record type.
- [x] **Planted bugs (changed 2026-11-07, human decision: ≥2 per target).** Exactly
      two planted bugs, ids `mfp-1` (deep) and `mfp-2` (shallow). Each is an
      ASan-detectable memory-safety error (out-of-bounds read or write) at a
      **single crash site** in its own function. The two functions differ, and
      neither contains any other crash site, so AFL-013 maps each bug to its own
      bucket and ground-truth entry. The source comment for each documents its id,
      function, trigger condition, expected ASan report type and depth class
      (shallow/deep as defined above). Each bug is reported by ASan with a stack
      whose `crash_site` is a target function (the bug's own); neither is an
      integer divide by zero (on arm64 that does not trap, `sdiv` gives 0, so it
      is never a crash); and `<name>.c` contains none of the forms banned by
      AFL-030's AC "Strict static source check", which holds the list (from
      AFL-030 condition-1 evidence, 2026-11-14). Test: the trigger and
      trigger-entry tests; review for no `/` or `%` on either bug's path; AFL-030's
      static test (or a grep against its list, if it has not landed) passes.
- [x] **Depth of `mfp-1`: staircase inputs (measured).** The source documents a chain of inputs
      `S0 → S1 → … → Sk` with **k ≥ 3**. `S0` is the shipped valid seed (below) and
      `Sk` is the trigger. For every i < k, `Si` has `outcome == "clean"`, and
      `edges(S(i+1)) − edges(Si)` is non-empty (each step reaches ≥1 new edge, so
      presence-only coverage would retain it). **≥1 step is cross-record:** it
      passes only because of a value set in an earlier record or the header (AC (e)).
- [x] **Trigger (`mfp-1`).** `Sk`, run through `Executor`, gives `outcome == "crash"`,
      `signal == SIGABRT` and `stderr` containing `ERROR: AddressSanitizer:` with
      the documented report type, under ADR-0002's forced `ASAN_OPTIONS`. The crash
      is at `mfp-1`'s site (definition above).
- [x] **Trigger (`mfp-2`).** The source documents a trigger input `T2` for `mfp-2`
      that differs from `S0` by exactly one byte substitution. Run through
      `Executor`, it gives `outcome == "crash"`, `signal == SIGABRT`, `stderr`
      containing `ERROR: AddressSanitizer:` with `mfp-2`'s documented report type,
      and the crash is at `mfp-2`'s site. (This is the shallow-depth proof.)
- [x] **`mfp-1` is not one mutation away (measured).** For the shipped seed `S0`
      (≤ 32 bytes), run every single-byte substitution (every position × all 256
      values, ≤ 8192 execs) through `Executor`. No result is a crash at `mfp-1`'s
      site. Crashes at `mfp-2`'s site are expected and allowed. The test may be
      marked slow.
- [x] **No other crashes or hangs.** Every documented benign and staircase input
      (`S0..S(k-1)`) has `outcome == "clean"` and exit status 0. None gives `"hang"`.
      In the single-byte sweep above, every crash is at the site of `mfp-1` or
      `mfp-2` (none at an undocumented site), and no result is `"hang"`.
- [x] **Seed.** A valid seed input `S0` (≤ 32 bytes, `outcome == "clean"`) is
      committed at `targets/seeds/<name>/S0`, where `<name>` is this target's
      binary name (`targets/bin/<name>`; currently `mini_format`, so
      `targets/seeds/mini_format/S0`, and the directory follows any rename under
      OQ 4). It is the only file in that directory and this target's sole initial
      corpus (AFL-011), and it is the same file the single-byte sweep, the `mfp-2`
      trigger and the `mfp-1` staircase above are measured against.
- [x] **Seed hash.** `S0`'s line in `targets/seeds/SHA256SUMS` (`sha256sum` output,
      `<hex>  <name>/S0`) is committed in the same change as `S0`, and in the same
      change as any later edit or rename. AFL-011's S0 pre-flight checks it.
- [x] **Ground truth.** `mfp-1` and `mfp-2` are each recorded with `target`,
      `function` and `file` in the same ground-truth mechanism AFL-009/010 adopt
      (proposed `targets/ground_truth.json`), so per-bug time-to-first-crash (PRD
      §8(c)) is computable by AFL-013. The two entries name different functions.
- [ ] **Retuning and freeze.** `mfp-1` (deep) is governed by AFL-011's AC
      "Pre-registered target retuning rule and freeze", which is the canonical
      text. Any retune of this target, with its triggering first-pilot numbers,
      and the freeze commit hash are recorded in this ticket's Log.
- [x] **Symbolizer-check trigger entries (added 2026-11-12, human decision).**
      Each planted bug of this target (`mfp-1`, `mfp-2`) has an entry in AFL-011's
      trigger table `targets/triggers.json` (format in AFL-011's AC "Pre-flight
      symbolizer check", bullet "Trigger table": key = the bug id in
      `ground_truth.json`, value = one known-crashing input as a lowercase hex
      string; if the file does not exist yet, this ticket creates it in that
      format). The input is one this ticket documents: `mfp-1`'s staircase end
      `Sk` and `mfp-2`'s `T2`. Test: for each of `mfp-1` and `mfp-2`, the entry's
      bytes, run through `Executor` against `targets/bin/<name>`, give
      `outcome == "crash"`, and `fuzzer.fuzzer.crash_site(stderr, "<name>.c")`
      equals that bug's `function` in `targets/ground_truth.json` (read from the
      file, not hard-coded).

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

- **Decision (human, 2026-11-07): `MAX_INPUT` stays 1024** (`src/fuzzer/mutator.py`,
  same in both arms). This target's stdin read cap must be consistent with it: read
  at most 1024 bytes (no larger cap, since mutants never exceed 1024 bytes; a smaller
  cap is allowed but wastes mutations beyond it, as with toy_parser/tlv_parser's 512).
- **Shared definitions in tests (human decision, 2026-11-12; AFL-029).** This target's tests use `fuzzer.fuzzer.seed_files` for the seeds-dir check and `fuzzer.fuzzer.crash_site(stderr, "<name>.c")` for every crash-site check from the start; no local seed listing or site regex.

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
Tester runs `pytest -m slow` (the depth sweeps) as a required step.

## Test (tester, 2026-11-15)
Verdict: **PASS** (all ACs except "Retuning and freeze", which stays open for AFL-011's pilot, as for AFL-009).
Clean checkout: working tree rsynced to a scratch copy (no .venv, targets/bin, results, caches),
`make -C targets` in the copy (all 4 binaries, no per-target flags), tests run with
`.venv/bin/python -m pytest --rootdir=<copy> -p no:cacheprovider --no-cov`; a probe test confirmed
`fuzzer.executor`/`fuzzer.fuzzer` import from the copy's `src`. AFL-016's files in the copy are byte-identical
to the repo at the end of testing. Own Executor probe and sweep scripts, independent of tests/test_mini_format.py.
- Build: Makefile diff is the TARGETS entry only; built through the pattern rule with REQUIRED_FLAGS + cov_rt.c.
- Scope: only `fread` (stdin, cap 1024) and `puts`; no open/socket/write. Record loop advances by >= 1 per
  iteration (every handler returns >= 1 or stops); inner loops bounded by len <= 8 / count <= (n-1)/2.
  Probe: 7 large/odd inputs (400 T records, B count 255, C len 255, 100 A records, 1024 NULs, 2004-byte input) all clean, exit 0.
- Format (a)-(e): confirmed in source. Cross-record measured: G with no prior T (S1+G02) is rejected
  and loses 5 edges vs S3; T under ver 1 is rejected (header state).
- Path diversity: default test passes (36 inputs, 36 distinct path_ids, all clean/exit 0, no ASan text).
- Planted bugs, own probe: mfp-1 S4 -> crash, SIGABRT, `heap-buffer-overflow`, `READ of size 1`,
  frames rec_get:97 then main:122, crash_site rec_get. mfp-2 T2 -> crash, SIGABRT, `stack-buffer-overflow`,
  `WRITE of size 1`, frames rec_data:57 then main:118, crash_site rec_data. Trigger exactness:
  A len 5..8 crash at rec_data, len 3, 4, 9 clean; T n / G idx for n = 1, 5, 255: idx n-1 and n+1 clean,
  idx == n crashes at rec_get; realloc path (T8 T2 G2) crashes at rec_get with heap-buffer-overflow
  (no stale pointer), T8 T2 G1 clean. No `/` or `%` in code (own grep after stripping comments);
  tests/test_target_static_check.py passes for mini_format.c (incl. injected-form cases).
- Staircase (own probe): S0..S3 clean exit 0; edges 17/17/20/23, new edges 2/3/3/1; S4 crashes at rec_get.
- mfp-1 not one mutation away: `pytest -m slow` (test_single_byte_sweep) PASSED (230 s). Own sweep:
  3072 execs, 3070 clean, 2 crashes (pos 5 = 0x05, 0x06, both rec_data), 0 hangs, no rec_get.
- Seed / hash: 12 bytes, sole file in targets/seeds/mini_format/; sha256 d2f6a167...df756 matches its SHA256SUMS line.
- Ground truth / triggers.json: mfp-1 rec_get, mfp-2 rec_data, target mini_format, file mini_format.c;
  trigger hex == S4 and == T2 byte-for-byte, each crashes at its ground-truth function. tlv-1/tlv-2 entries
  unchanged (test_tlv_parser.py passes in the copy, which pins them to T1 and the tlv-2 staircase end).
  toy-1/toy-2 entries (AFL-011) not checked, as briefed.
- Gates in copy: test_mini_format 6 passed, test_target_static_check 19 passed, test_tlv_parser 6 passed; ruff check . clean.
Mutation sanity (scratch copies only, each rebuilt):
- M1 remove mfp-2 (`len > 8` -> `len > 4`): test_trigger_table and test_mfp2_shallow FAIL.
- M2 remove mfp-1 (`idx > g_tsz` -> `idx >= g_tsz`): test_trigger_table and test_mfp1_deep_staircase FAIL.
- M3 make mfp-1 shallow (table pre-allocated with size 1, no ver gate on G; S0 pos 8 'B' -> 'G' crashes):
  slow sweep FAILS (`'rec_get' not in {'rec_data': 2, 'rec_get': 1}`); default test_path_diversity also fails (35/36).
- M4a branch added after the crash line in rec_get (`if (c == 7) puts(...)`): all 6 default tests pass, S3 -> S4 still +1 edge.
- M4b remove the `idx == g_tsz` puts line: S3 -> S4 adds 0 edges; test_mfp1_deep_staircase FAILS.
Non-blocking:
- AFL-010 F2 (block pruning drops the crash block's edge): mfp-1 is not exposed. S4's new edge is the
  `one-past` block at line 96, before the crash line; the crash block at line 97 is also run by S3, so it
  never was S4's new edge (M4a shows a branch after the crash line leaves the step intact). The step does
  depend entirely on line 96 (M4b): any edit removing it breaks the staircase AC; the reviewer's k = 3
  alternative (S0 -> S1 -> S2 -> S2+G03) would then be the fallback. The test catches this.
- The sweep takes about 4 min on this machine (fork per exec); fine for `-m slow`.

## Closure (crew-lead, 2026-11-15)
DoD verified; ticket moved to done.
- ACs: 14 of 15 ticked, each backed by the re-review APPROVE (Log, 2026-11-15) and the tester's
  PASS on a clean-checkout copy (## Test, 2026-11-15). No AC was ticked at close. Spot-checked
  here: S0 is the sole file in targets/seeds/mini_format/, 12 bytes, sha256 d2f6a167...df756
  matches its SHA256SUMS line; ground_truth.json maps mfp-1 -> rec_get, mfp-2 -> rec_data;
  triggers.json has both entries; the Makefile diff is the TARGETS entry only.
- "Retuning and freeze" stays open by design. It is carried by AFL-011's AC "Pre-registered
  target retuning rule and freeze", which logs any retune (with first-pilot numbers) and the
  freeze hash in this ticket. Precedent: AFL-009 was closed on 2026-11-12 with its matching
  "Retuning and freeze" AC open for the same reason (tickets/done/AFL-009-toy-parser-target.md).
- Tester's non-blocking notes, recorded:
  - the S3 -> S4 staircase step depends on the line-96 `puts("one-past")` (mutant M4b removes
    it and the staircase test fails); the fallback is the k = 3 chain S0 -> S1 -> S2 -> S2+G03;
  - mfp-1 is not exposed to AFL-010 F2 (block pruning of the crash block's edge);
  - the slow single-byte sweep takes about 4 minutes (fork per exec); fine under `-m slow`.
- Gates: the done-gate hook (gate_ticket_done.py) ran ruff, mypy and pytest on the move.
- OQ 1, 4, 5 defaults (heap-buffer-overflow READ for mfp-1, name `mini_format.c`, no line cap)
  remain marked "lead to confirm".
- The commit must reference AFL-016 and land on main before the AFL-011 baseline
  (2026-11-16 12:00 ET) per the lead's cutoff (human's step).

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
- 2026-11-07 — added S0 integrity pre-flight AC (human decision) (req-engineer)
- 2026-11-07 — see AFL-019: `S0` must be non-empty; the S0 pre-flight rejects a zero-length seed (req-engineer)
- 2026-11-07 — batch grooming: AFL-019 is folded into AFL-011, so the non-empty-S0 rule above now lives in AFL-011's S0 pre-flight AC block; recorded `MAX_INPUT` = 1024 decision and read-cap consistency in Technical notes (human decision) (req-engineer)
- 2026-11-12 — Test approach: tester runs `pytest -m slow` (the S0 depth sweeps, excluded from the default run) as a required step (human decision) (req-engineer)
- 2026-11-12 — Technical notes: tests use AFL-007's `seed_files` and `crash_site` from the start, per AFL-029 (human decision, 2026-11-12) (req-engineer)
- 2026-11-12 — added AC "Symbolizer-check trigger entries": `mfp-1` and `mfp-2` each get one known-crashing input in AFL-011's `targets/triggers.json`, tested to give `crash_site()` equal to its `ground_truth.json` function, for AFL-011's per-bug pre-flight symbolizer check (human decision, 2026-11-12) (req-engineer)
- 2026-11-14 — extended the "Planted bugs" AC: `mfp-1` and `mfp-2` are ASan-reported with a stack at a target function, neither is an integer divide by zero (no trap on arm64), and the source passes AFL-030's static source check (list kept in AFL-030 only) (from AFL-030 condition-1 evidence, 2026-11-14) (req-engineer)
- 2026-11-15 — implemented (developer): targets/mini_format.c, seeds/mini_format/S0 (+SHA256SUMS), ground_truth.json and triggers.json entries (mfp-1 rec_get, mfp-2 rec_data), Makefile TARGETS entry, tests/test_mini_format.py. OQ 1, 4, 5 adopted at proposed defaults: mfp-1 is a heap-buffer-overflow READ (tlv-1 is a stack write), name `mini_format.c`, no hard line cap (proposed default adopted by orchestrator, 2026-11-15; lead to confirm). No planted bug in main() (lead decision); both bugs are ASan-reported in distinct non-main functions, no divide or modulo anywhere. The AFL-030 static-check part of the Planted bugs AC is verified once AFL-030 lands (source written to pass it as worded; the test here carries the same banned-form list as test_tlv_parser.py). Measurements: S0 12 bytes, 17 edges; 41 benign inputs, 34 distinct path_ids, all clean; staircase S0..S4 new edges 2/3/3/1 (S4 crashes in rec_get, heap-buffer-overflow); single-byte sweep of S0 (3072 execs): only 2 crashes, both rec_data (len 5, 6), none in rec_get, no hangs. Retuning and freeze AC left open (belongs to AFL-011's pilot). Moved to review.
- 2026-11-15 — review (reviewer): BOUNCE to in-progress, one blocking item.
  BLOCKING (AC "Path diversity"): the AC requires the documented benign set's `path_id`s to be
  pairwise distinct and the set to include the empty input and a magic-only input. Measured
  through `Executor`: 41 inputs, 34 distinct ids, 5 collision groups:
  {b"", b"M", b"MF", b"MF\x01"}, {H1+b"\x01", H1+b"?"}, {H1+b"A\x00", H1+b"A\x00A\x00"},
  {H1+b"B\x01kv", H1+b"B\x02kvkv"}, {H2+b"T\x04G\x00", H2+b"T\x04G\x03"}. The empty input and
  the magic-only input b"MF" (labelled so at tests/test_mini_format.py:29; the magic is the
  2 bytes "MF" per the header comment, mini_format.c:6) share a path because main()'s
  `n < 4` test short-circuits before the magic compare (mini_format.c:105), so no pruning of the
  list alone can meet the AC. tests/test_mini_format.py:84 asserts only `len(ids) >= 20`, which is
  weaker than the AC, so the test passes while the AC fails; the AC box had been ticked.
  Fix: (1) in main(), check the magic before the length, e.g. `n < 2 || in[0] != 'M' ||
  in[1] != 'F'` then `n < 4` as separate tests, so b"" and b"MF" take different edges;
  (2) prune BENIGN so every entry has a distinct path_id (keep >= 20, keep empty, magic-only,
  truncated record, unknown type); (3) assert `len(ids) == len(BENIGN) >= 20`; (4) re-run the
  default and `-m slow` tests and re-record the S0 edge count, staircase deltas and sweep result
  in this Log (S0, its hash, T2 and Sk do not change).
  Verified, no change needed: Build (Makefile diff is the TARGETS entry only); Scope (stdin
  only, fread cap 1024, loops bounded by n, len <= 8 or count <= (n-1)/2); Format structure
  (a)-(e) (ver changes parsing, record loop, A/B/C/T/G + default, B count sets layout, G needs
  T's table and T needs ver 2); Planted bugs (ad-hoc runs: mfp-1 heap-buffer-overflow READ,
  #0 rec_get mini_format.c:97; mfp-2 stack-buffer-overflow WRITE, #0 rec_data mini_format.c:57;
  one crash site per function, neither in main, no `/` or `%` in code, banned-form grep passes;
  the AFL-030 static-check part is deferred to AFL-030 as the 2026-11-15 developer Log line says);
  Staircase (deltas 2/3/3/1, all prefixes clean, S2->S3 cross-record); both triggers (SIGABRT,
  report type, site); single-byte sweep (`pytest -m slow` passed: no rec_get crash, only
  rec_data, no hang); Seed (12 bytes, sole file) and Seed hash (sha256 d2f6a167...df756 matches
  the SHA256SUMS line); Ground truth and triggers.json (same target/function/file schema as
  toy/tlv; trigger hex equals Sk and T2; neither file has a depth field for any target, depth
  lives in the source comment); Symbolizer-check trigger entries (test reads functions from
  ground_truth.json). Retuning and freeze stays open (AFL-011 pilot), as for AFL-009.
  Q1, Q4, Q5 are recorded with the required "(proposed default adopted by orchestrator,
  2026-11-15; lead to confirm)" marker; none contradicts an AC.
  Staircase "idx == size" branch (mini_format.c:96): accepted. It is a real edge on the bug's
  path, reached only by crashing inputs, so it gives the fuzzer no gradient and never enters the
  clean-exec `edges` metric (ADR-0005); it does not make mfp-1 shallower (the sweep confirms).
  Note: a k = 3 chain S0 -> S1 -> S2 -> S2+"G\x03" (delta 3) meets the AC without it.
  NON-BLOCKING: tests/test_mini_format.py:24-27 builds STAIRCASE with None placeholders, which
  gives 3 mypy operator errors (tests are outside the `mypy src` gate); build it as plain bytes
  while the file is open. Comment mini_format.c:39 could say "S4 = S3 with idx 02 -> 03" so the
  S3 -> S4 step reads as a single substitution. Gates: ruff check . and mypy src pass; default
  tests 6 passed; -m slow passed.
- 2026-11-15 — bounce 1 fixed (developer): main() now checks the magic byte by byte before any length check (n<1 / 'M', n<2 / 'F', n<4), so empty, "M", "MF" take different paths. BENIGN pruned to 36 inputs with 36 pairwise-distinct path_ids (test asserts len(ids) == len(BENIGN) >= 20); includes empty, "MF", truncated record, unknown type. STAIRCASE built as plain bytes; S4 comment reads "S3 with idx 02 -> 03". S0, SHA256SUMS, T2, Sk, triggers.json unchanged. Re-measured: S0 17 edges; staircase new edges S1 2, S2 3, S3 3, S4 1 (S4 crash_site rec_get); single-byte sweep: 2 crashes, both rec_data, no hangs. Default and slow tests pass, ruff and mypy src pass. Moved to review.
- 2026-11-15 — removed the local BANNED list and banned-form loop from tests/test_mini_format.py (list lives in AFL-030 only; tests/test_target_static_check.py globs targets/*.c and covers mini_format.c); test renamed test_ground_truth_and_source_docs, no-/-or-% check kept (developer)
- 2026-11-15 — re-review after bounce 1 (reviewer): APPROVE, moved to testing. (1) main() checks magic byte by byte before the length (mini_format.c:105-107); b"", b"M", b"MF" give 3 distinct path_ids. (2) BENIGN is 36 inputs, 36 distinct path_ids measured through Executor, all clean, incl. empty, "MF", truncated H1+"A", unknown H1+"?" (tests/test_mini_format.py:28-37). (3) floor kept: line 70 asserts `len(set(BENIGN)) == len(BENIGN) >= 20`, line 77 `len(ids) == len(BENIGN)`. (4) re-measured: S0 17 edges; staircase deltas 2/3/3/1, S0..S3 clean, S4 crash at rec_get; `pytest -m slow` sweep passed (no rec_get, no hang; analytically only pos 5 = 0x05/0x06 crash, at rec_data). (5) STAIRCASE is plain bytes (:24-27); no mypy operator errors remain (only import-untyped). (6) comment mini_format.c:39 reads "S4 = S3 with idx 02 -> 03". (7) no local BANNED list in tests/test_mini_format.py; test_target_static_check.py globs targets/*.c and passes on mini_format.c; renamed test keeps ground-truth, source-doc, stdin-only and no-/-or-% checks (:55-65). Bug constraints hold (heap-buffer-overflow READ rec_get, stack-buffer-overflow WRITE rec_data, no / or % in code). S0 bytes unchanged, sha d2f6a167...df756 matches SHA256SUMS; Makefile diff is the TARGETS entry only. Gates: ruff check . and mypy src pass; default 6 + static-check 19 passed; -m slow passed.
- 2026-11-15 — test (tester): PASS on a clean-checkout copy; default, static-check and `-m slow` tests pass; own Executor probe and sweep confirm both bugs, triggers, staircase 2/3/3/1, sweep 2 rec_data crashes / no rec_get / no hang, S0 hash; 4 of 4 bug mutants caught (M3 shallow by the slow sweep); F2 not exposed. Left in testing for crew-lead close. Retuning and freeze AC stays open (AFL-011).
- 2026-11-15 — DoD verified, moved to done (crew-lead). 14/15 ACs ticked on reviewer APPROVE and tester PASS evidence; "Retuning and freeze" left open, carried by AFL-011, same as AFL-009 (closed 2026-11-12 with that AC open); tester's non-blocking notes (line-96 dependency / k = 3 fallback, F2 not exposed, ~4 min slow sweep) recorded in Closure. Commit must reference AFL-016 (human's step).
- 2026-11-15 — retuned (AFL-035): mfp-1 (rec_get) retuned once under the pre-registered retuning rule; first pilot (run on d9a22db, results/pilot/first_pilot, seeds 2000..2002, 3 trials per target x arm, c = 3; found = a crash_events.csv row whose crash_site equals the bug's ground_truth function): mfp-1 uniform 0/3, fast 0/3 -> (i) yes, (ii) no; staircase, S0, odds and sweeps are in AFL-035's Log (developer)
