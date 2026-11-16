---
id: AFL-010
title: tlv_parser target + documented bugs
requirement: SC1
paper_ref: Klees § performance measures / ground truth (known bugs as ground truth)
module: targets/tlv_parser.c
depends_on: [AFL-003]
status: done
owner: developer
---

## Goal
A more realistic target: a Type-Length-Value parser that trusts its length byte
behind a flawed guard, so a length byte that passes the guard and exceeds 64
(type 0x01 with length 65..128, or any other type with length 65..255; type 0x01
with length > 128 is rejected) overflows a 64-byte stack buffer and
AddressSanitizer catches it. This is ground truth for SC1 and for
time-to-first-crash (PRD §8).

Open questions (PRD silent or ambiguous; resolve before leaving backlog):
- ~~**Crash classification.** By default ASan reports the overflow and exits with a
  non-zero code, not SIGABRT. Under FR-2's rule (SIGSEGV/SIGABRT = crash) this bug
  would go undetected unless ASan is set to abort (e.g.
  `ASAN_OPTIONS=abort_on_error=1`) or FR-2 is widened. This needs a decision; see
  AFL-003.~~
  **Resolved (human, 2026-11-07) — ADR-0002.** The executor forces
  `ASAN_OPTIONS=abort_on_error=1:detect_leaks=0:symbolize=1`, replacing any
  inherited value. The overflow therefore ends in SIGABRT, a crash under FR-2 as
  written. See `docs/adr/0002-asan-configuration.md`.
- End-to-end discovery by the fuzzer (SC1) depends on AFL-007 and is verified
  there.
- ~~**Number of bugs** (implicit: the ticket and INDEX said "documented bug",
  singular, and the architect's methodology flag notes that tlv-1 is one mutation
  away).~~ **Resolved (human, 2026-11-07).** PRD §8 now requires ≥2 planted bugs per
  experiment target, at distinct crash sites in distinct functions, at least one
  shallow and at least one deep, each in ground truth. tlv_parser gets exactly two.
  `tlv-1` (length byte, guarded) is the **shallow** one, since one substitution of
  the length byte in a benign seed triggers it. The new `tlv-2` must be the
  **deep** one. Shallow and deep are AFL-016's "Depth definitions", verbatim: both
  measured against the shipped seed `S0` through `Executor`; *at bug X's site*
  means the first ASan stack frame in the target's source file names X's
  function. Shallow means ≥1 single-byte substitution of `S0` crashes at the site.
  Deep means none does, and a documented staircase `S0 → … → Sk` (k ≥ 3, each step
  clean and adding ≥1 new edge) reaches it.
- ~~*New:* SC1 requires the fuzzer to discover **each** planted bug end to end, which
  now includes the deep `tlv-2`. AFL-016's one-time retuning rule covers only
  `mfp-1`. Should the same rule apply to `tlv-2`? Needs a crew-lead/Vision decision.~~
  **Resolved (human, 2026-11-07).** Yes. `tlv-2` falls under AFL-011's canonical
  AC "Pre-registered target retuning rule and freeze" (see the Retuning and freeze
  AC below).

## Acceptance criteria
- [ ] `make -C targets` builds `targets/bin/tlv_parser` with
      `-fsanitize-coverage=trace-pc-guard` and AddressSanitizer.
- [ ] The planted bug is documented in the source with its location (the `memcpy`
      into `field`), its trigger (length byte > 64 and not rejected by the guard;
      for type 0x01, length byte in 65..128) and the expected ASan report
      (stack-buffer-overflow).
- [ ] A known triggering input on stdin (length byte `in[1]` > 64, except that
      type `in[0] == 0x01` with `in[1]` > 128 is rejected by the guard and exits
      0; so type 0x01 triggers only with 65 ≤ `in[1]` ≤ 128) produces an ASan
      stack-buffer-overflow report. Two bytes of input suffice (e.g. `01 50`);
      the documented trigger is T1 = `01 50 41 42 43 44`.
- [ ] A benign input (length byte ≤ 64) exits with status 0 and no sanitizer
      report.
- [ ] Under the agreed ASan configuration, the triggering input is classified as
      a crash by the FR-2 rule (see open question).
- [ ] The target reads input only from stdin and makes no network calls (NFR-6).
- [ ] **Guarding branch (human decision 2026-11-07).** The overflow sits behind an
      insufficient guard: a type check plus a flawed length bound, e.g.
      `if (type == 0x01 && len > 128) return 0;`, so the overflow is reachable only
      with `len` in 65..128 on one side of the branch. The developer chooses the
      exact guard, but all of these must hold:
      (a) the overflow is reachable only via a distinct edge (a coverage edge not
      taken by any input on the benign side of the guard), verified by comparing
      the edge sets of the two inputs in (b);
      (b) the source documents one crashing input and one benign input for each
      side of the guard (at minimum: crashing, benign-below-bound, and
      rejected-by-guard), with the expected outcome of each (ASan report or exit 0);
      (c) the bug remains a single crash site (one `memcpy` line), so de-duplication
      (AFL-013) sees one bucket, not several.
      The trigger/benign inputs in the earlier criteria and technical notes
      are to be updated to match the guard.
- [ ] **Fallback.** If the human or architect rejects the guard, the criterion above
      is waived only if the branch-free bug is documented as a known limitation (no
      coverage gradient toward the bug) in both the target's header comment and the
      report's threats-to-validity section, with the log below recording the decision.
- [ ] **Two planted bugs (human decision 2026-11-07, PRD §8).** Exactly two planted
      bugs: `tlv-1` (shallow, the existing guarded `memcpy` in `main`) and `tlv-2`
      (deep, new). `tlv-2` is an ASan-detectable memory-safety error at a **single
      crash site** in its own function, which is not `main`, and that function
      contains no other crash site. So AFL-013 maps the two bugs to distinct
      buckets. Each bug's source comment documents its id, function, trigger,
      expected ASan report and depth class. `tlv-2` is reported by ASan with a
      stack whose `crash_site` is a target function (`tlv-2`'s own); it is not an
      integer divide by zero (on arm64 that does not trap, `sdiv` gives 0, so it
      is never a crash); and `tlv_parser.c` contains none of the forms banned by
      AFL-030's AC "Strict static source check", which holds the list (from
      AFL-030 condition-1 evidence, 2026-11-14). Test: the `tlv-2` depth and
      trigger-entry tests below; review for no `/` or `%` on the bug's path; AFL-030's
      static test (or a grep against its list, if it has not landed) passes.
- [ ] **Seed.** A seed input `S0` (≤ 32 bytes, `outcome == "clean"`) is committed
      at `targets/seeds/tlv_parser/S0` and is the only file in that directory.
      It is this target's sole initial corpus (AFL-011), and it is the same file
      the single-byte sweep, the `tlv-1` trigger and the `tlv-2` staircase below
      are measured against.
- [ ] **Seed hash.** `S0`'s line in `targets/seeds/SHA256SUMS` (`sha256sum` output,
      `<hex>  tlv_parser/S0`) is committed in the same change as `S0`, and in the
      same change as any later edit to it. AFL-011's S0 pre-flight checks it.
- [ ] **`tlv-1` is shallow (measured, via `Executor`).** The source documents a
      `tlv-1` trigger that differs from `S0` by exactly one byte substitution. It
      gives `outcome == "crash"`, `signal == SIGABRT`, and an ASan
      stack-buffer-overflow report whose first in-source frame is `main`.
- [ ] **`tlv-2` is deep (measured, via `Executor`).** No single-byte substitution of
      `S0` (every position × all 256 values) crashes at `tlv-2`'s site. The source
      documents a staircase `S0 → S1 → … → Sk`, k ≥ 3, where `Sk` crashes at
      `tlv-2`'s site (SIGABRT, documented ASan report) and each `Si` (i < k) is
      clean with `edges(S(i+1)) − edges(Si)` non-empty.
- [ ] **No undocumented crashes or hangs.** In the single-byte sweep over `S0`, every
      crash is at `tlv-1`'s or `tlv-2`'s site and no result is `"hang"`.
- [ ] **Ground truth.** `tlv-1` (`function: main`) and `tlv-2` (its own function)
      each have an entry (`target`, `function`, `file`) in
      `targets/ground_truth.json`.
- [ ] **Retuning and freeze.** `tlv-2` (deep) is governed by AFL-011's AC
      "Pre-registered target retuning rule and freeze", which is the canonical
      text. Any retune of this target, with its triggering first-pilot numbers,
      and the freeze commit hash are recorded in this ticket's Log.
- [ ] **AFL-007 fixture kept current (human decision, 2026-11-07).** If this
      ticket changes tlv_parser's overflow (`tlv-1`) ASan report, the same change
      re-captures AFL-007's `tests/fixtures/` tlv_parser report from the new build
      and updates the source commit recorded in that fixture. Test: AFL-007's
      fixture staleness integration test passes against the new build.
- [ ] **Symbolizer-check trigger entries (added 2026-11-12, human decision).**
      Each planted bug of this target (`tlv-1`, `tlv-2`) has an entry in AFL-011's
      trigger table `targets/triggers.json` (format in AFL-011's AC "Pre-flight
      symbolizer check", bullet "Trigger table": key = the bug id in
      `ground_truth.json`, value = one known-crashing input as a lowercase hex
      string; if the file does not exist yet, this ticket creates it in that
      format). The input is one this ticket documents: `tlv-1`'s
      single-substitution trigger and `tlv-2`'s staircase end `Sk`. Test: for each
      of `tlv-1` and `tlv-2`, the entry's bytes, run through `Executor` against
      `targets/bin/tlv_parser`, give `outcome == "crash"`, and
      `fuzzer.fuzzer.crash_site(stderr, "tlv_parser.c")` equals that bug's
      `function` in `targets/ground_truth.json` (read from the file, not
      hard-coded).

## Technical notes (architect)
- **Expected report:** an ASan `stack-buffer-overflow` WRITE inside the memcpy
  interceptor (`__asan_memcpy`), with the next frame at `main tlv_parser.c:69`. Under
  `ASAN_OPTIONS=abort_on_error=1` (AFL-003, → `docs/adr/0002-asan-configuration.md`,
  accepted 2026-11-07) the process ends with SIGABRT, a crash under FR-2 as written.
  ADR-0002's "What AFL-010 relies on" section is the "agreed ASan configuration"
  the AC refers to.
- **Trigger:** T1 = `b"\x01\x50ABCD"` (hex `015041424344`, length byte 0x50 = 80;
  S0 with byte 1 substituted). Benign: `b"\x01\x04ABCD"` (= S0), `b""`, and the
  rejected-by-guard `b"\x01\x90ABCD"` (length byte 0x90 = 144) exit 0.
- The overflow fires for any `in[1] > 64` that passes the guard at
  `tlv_parser.c:65` (`type == 0x01 && len > 128` returns 0): type 0x01 with
  `in[1]` in 65..128, or any other type with `in[1]` in 65..255. This holds
  whatever the real input length, because memcpy reads from the 512-byte `in`
  buffer. So a trigger needs only 2 bytes.
- Add ground-truth entry `tlv-1` (`function: main`, `file: tlv_parser.c`) to
  `targets/ground_truth.json`, as in AFL-009.
- `printf` writes to stdout. The executor discards stdout, so no change is needed.
- Same Makefile changes as AFL-009: `-fno-omit-frame-pointer` and the coverage runtime.
- **Shared definitions in tests (human decision, 2026-11-12; AFL-029).** This target's tests use `fuzzer.fuzzer.seed_files` for the seeds-dir check and `fuzzer.fuzzer.crash_site(stderr, "tlv_parser.c")` for every crash-site check from the start; no local seed listing or site regex.
- **Methodology flag (resolved: guarded branch (human decision, 2026-11-07)):** this
  bug is one mutation away from any 2-byte seed; for S0 (type 0x01), 1/4 of random
  second bytes trigger it (64 of 256 values, 65..128, matching the sweep). Both arms
  will probably find it within seconds, so TTFC will not separate the schedules. If
  Vision wants a target that discriminates, gate the overflow behind deeper checks
  (e.g. a type check plus a magic header).

## Test approach (tester)
Build, run the trigger and benign inputs, and assert the ASan report or clean
exit. Check the trigger's classification through the executor once AFL-003 lands.
Tester runs `pytest -m slow` (the depth sweeps) as a required step.

## Review (reviewer, 2026-11-14)
Verdict: **changes requested** (first bounce). The code and tests are sound and
every behavioural claim measures true. Two documented facts about `tlv-2` are
wrong, and the ticket text the guarding-branch AC says must be updated was not.

Evidence gathered: I did not run `make`. The binary is current: `bin/tlv_parser`
was built at 21:47:27, after `tlv_parser.c` (21:47:14), `Makefile` (Nov 12) and
`cov_rt.c` (Nov 7). `pytest -m "not slow" tests/test_tlv_parser.py
tests/test_toy_parser.py tests/test_fuzzer.py` gives 50 passed, 3 deselected;
the fixtures' `make` was a no-op and the binary's mtime did not change.
`ruff check .` and `mypy src` are clean. My own `Executor` probes are below.

Per AC:
- Build: pass. Makefile `REQUIRED_FLAGS` has `-fsanitize=address
  -fsanitize-coverage=trace-pc-guard -fno-omit-frame-pointer`.
- Bug documented (location, trigger, report): pass for `tlv-1`
  (`tlv_parser.c:11-24`). Fail for `tlv-2`; see R1 and R2.
- Triggering input gives an ASan stack-buffer-overflow: pass. T1 = `015041424344`
  gives a WRITE of size 80, frame #0 `__asan_memcpy`, #1 `main tlv_parser.c:69`.
- Benign gives exit 0 and no report: pass (`b""`, S0, and `01 90 ...` rejected).
- FR-2 classification under ADR-0002: pass. T1 and S3 each end in SIGABRT and
  are classified `crash`.
- stdin only, NFR-6: pass. The only I/O is `fread(stdin)` and `printf`. No
  file, network, env or exec calls.
- Guarding branch: (a) pass. The `len > 64` block at `:66-68` is taken iff the
  memcpy overflows (type != 1 is never rejected; type 1 passes only 65..128), and
  the test asserts T1.edges − S0.edges − REJECTED.edges is non-empty.
  (b) pass in the source (`:19-22`). (c) pass: one memcpy (`:69`); the other
  accesses in `main` are bounded (`off + 2 <= n`, and the memcpy reads stay
  inside `in[512]`). The AC's last sentence, which requires the earlier ACs and
  the Technical notes to be updated to match the guard, is not met; see R4.
- Two planted bugs: pass, apart from R1 and R2. `parse_ext` is not `main` and has
  one crash site (`:49`). Both bugs give an ASan report with `crash_site` equal to
  the ground-truth function. There is no integer divide. The local `BANNED` list
  in `tests/test_tlv_parser.py` matches AFL-030's 18 forms verbatim, comments are
  stripped, and no `/` or `%` appears in the code. AFL-030 has not landed, so this
  stands in for its static test.
- Seed: pass. S0 = `01 04 41 42 43 44`, 6 bytes, clean, the only file in the dir.
- Seed hash: pass. `shasum -a 256` gives `0a00d89f…63be`, which matches the
  SHA256SUMS line. The toy line is unchanged (git diff shows only the appended
  line).
- `tlv-1` shallow: pass. T1 differs from S0 at one byte; SIGABRT;
  stack-buffer-overflow; `crash_site == "main"`.
- `tlv-2` deep: pass, measured. Staircase new edges: S0→S1 {10,12,13},
  S1→S2 {15}, S2→S3 {16}. S0, S1 and S2 are clean; S3 crashes at `parse_ext`
  with heap-buffer-overflow READ and SIGABRT, deterministically (5/5 runs).
- No undocumented crashes or hangs: pass. I counted the sweep per site, which the
  developer did not print: 1536 runs, 64 crashes, all at byte 1 and all in `main`
  (values 65..128), 0 in `parse_ext`, 0 hangs, 1472 clean. The test's
  set-membership asserts are enough for the AC. The counts are only useful for the
  report, so this is not blocking (N2).
- Ground truth: pass. `tlv-1` maps to `main` and `tlv-2` to `parse_ext`. The toy
  entries are unchanged in the diff.
- Retuning and freeze: n/a until AFL-011's pilot. The pointer AC is in place.
- AFL-007 fixture: pass for now. The header sha256 `0cd7631b…3272` equals the
  current `tlv_parser.c`. Frame #0 is `__asan_memcpy` above `#1 main
  tlv_parser.c:69`. `test_fixture_not_stale` passes. R3 applies once the source
  changes.
- Trigger entries: pass. `triggers.json` holds T1 and S3. The test reads the
  function from `ground_truth.json` and checks that the bytes equal T1 and the
  staircase end.
- `test_toy_parser` filter: not vacuous. `gt["toy-1"]` and `gt["toy-2"]` are
  still indexed directly at `:45` (KeyError if missing), and every toy_parser
  entry is still checked in the loop.

Required changes:
1. **`tlv_parser.c:28`, `tlv-2` trigger is wrong.** It says "index byte >= 16".
   Measured over all 256 values of the last byte of `S0 + 7E 02 58 xx`: 0..3 are
   clean and 4..255 crash at `parse_ext` (252/256; boundary `...5803` clean,
   `...5804` crash). State the trigger as index byte >= 4 (outside the 4-byte
   block). A planted bug's ground-truth trigger must be exact (the "Two planted
   bugs" AC; the report will quote it).
2. **`tlv_parser.c:31`, the depth rationale is false.** It says "it needs 7E, 'X'
   and the index byte, all absent from S0". The index byte is not absent: every
   byte of S0 from 2 on is >= 4. Example: `01 00 7E 42 58 44`, three
   substitutions of S0 (bytes 1, 2 and 4), crashes at `parse_ext`, and
   `01 00 7E 42 43 44` is a clean intermediate. The measured depth class still
   holds (no single substitution reaches it). Reword the rationale to what is
   true: 0x7E and 'X' are absent from S0, and once those two are in place the
   index condition is almost free. Optionally record the 3-substitution minimum
   found here.
3. **Keep the fixture current after 1 and 2.** Editing the comment changes the
   source sha256 recorded in `tests/fixtures/tlv_parser_asan_memcpy.txt`. Keep
   the comment's line count unchanged so the memcpy stays at `:69`. Rebuild once
   the other agent's run has finished, then re-capture the fixture or update its
   header sha256 and confirm frame #1 still reads `main tlv_parser.c:69`. Re-run
   `test_fixture_not_stale` and the `tlv_parser` tests. S0 and SHA256SUMS are
   unaffected.
4. **Ticket text, guarding-branch AC (last sentence).** "The trigger/benign
   inputs in the earlier criteria and technical notes are to be updated to match
   the guard" was not done:
   - the AC "A known triggering input" says "length byte > 64 followed by enough
     bytes", which ignores the type 0x01 && len > 128 rejection and the fact
     that 2 bytes suffice;
   - the Technical notes still say "next frame at `main tlv_parser.c:19`" (now
     `:69`);
   - they still say "The overflow fires for any `in[1] > 64`" (false for type
     0x01 with len > 128);
   - they still give trigger `\x01\x50 + A*80` rather than the documented T1.
   This is AC and notes text, so the req-engineer or orchestrator updates it and
   logs it.

Non-blocking notes:
- N1. **`main` as a bug function, and dedup across targets.** Within
  `tlv_parser`, `main` is a sound single site (see Guarding branch (c)). Across
  targets it is a hazard owned by AFL-013/AFL-011, not this ticket.
  `harness/dedup.py:49-50` builds `{function: bug_id}` over all of ground truth
  when `target is None`. With `tlv-1 = main`, any `main` crash in toy_parser, or
  in AFL-016's mini-format target, would map to `tlv-1`, and a second target
  with a bug in a same-named function would silently overwrite the dict entry.
  Recommend that AFL-013/AFL-011 always pass `target` (or key on `(target,
  function)`), and that AFL-016 avoid putting a bug in `main`. The AC mandates
  `function: main`, so this does not block AFL-010.
- N2. Record the per-site sweep counts above in the Log or the report (64 at
  `main`, 0 at `parse_ext`, 0 hangs).
- N3. **Reachability.** Neither 0x7E nor 'X' is in S0, and clone-insert copies
  only existing bytes. So the two rare steps need a random-byte insert or
  overwrite (about 1/256 each, at a constrained offset), and the index step is
  then about 98% free. The bug is plausibly reachable but hard under blind
  mutation. Whether TTFC separates the arms is for AFL-011's pilot and the
  retuning rule.

## Re-review (reviewer, 2026-11-14, after bounce 1)
Verdict: **changes requested** (second bounce; this hits the "ticket bounces
twice" stop condition, so the orchestrator pauses for the human). R1 to R4 are
fixed. One new defect: the source's `tlv-1` trigger does not match the AC text
that R4 restated. I missed it in bounce 1; the R4 restatement made the gap
explicit.

Evidence: I did not run `make`. `bin/tlv_parser` (22:03:18) is newer than
`tlv_parser.c` (22:03:09), `Makefile` (Nov 12) and `cov_rt.c` (Nov 7), and its
mtime did not change during my runs. `shasum -a 256 tlv_parser.c` gives
`d8e6d92e…d590`, which equals the fixture header. `ruff check .` and `mypy src`
are clean. `pytest -m "not slow"` on test_tlv_parser, test_toy_parser and
test_fuzzer gives 50 passed, 3 deselected. `pytest -m slow
tests/test_tlv_parser.py` gives 1 passed (87 s). I also ran the binary directly
under ADR-0002's `ASAN_OPTIONS`.

- R1, pass. `tlv_parser.c:28` reads "an index byte >= 4". Probes: `...7E 02 58
  03` exits 0; `...7E 02 58 04` and `...58 10` exit 134 with heap-buffer-overflow
  in `parse_ext tlv_parser.c:49`.
- R2, pass. `:31-32` now says the bug needs 0x7E and 'X', neither in S0, and
  that `01 00 7E 42 58 44` takes 3 substitutions. Probes: that input crashes at
  `parse_ext :49`, and `01 00 7E 42 43 44` exits 0.
- R3, pass. The fixture header sha256 equals the current source. Frame #0 is
  `__asan_memcpy`, #1 is `main tlv_parser.c:69`, and SUMMARY reads `:69 in main`.
  The file is still 79 lines, the memcpy is still at `:69` and the read at `:49`.
  `test_fixture_not_stale` passes.
- R4, pass for the four listed items. The "planted bug is documented" and "A
  known triggering input" ACs state the guard and 2-byte sufficiency, and give T1.
  The Technical notes give `:69`, T1, the rejected input `01 90 …`, and the
  overflow claim restricted to inputs passing the guard at `:65`. All of these
  match the source and my probes (`0150` crashes; `01c8` and `01904142434444`
  exit 0).
- No regressions: `triggers.json`, `ground_truth.json`, S0 and SHA256SUMS are
  unchanged, and the code below line 38 is unchanged (comment-only edits).

Required change:
5. **`tlv_parser.c:13-14`, the `tlv-1` trigger is incomplete (AC "planted bug
   is documented", as restated).** The source says "Trigger: len byte in
   65..128". The AC now requires "length byte > 64 and not rejected by the
   guard; for type 0x01, length byte in 65..128". For any type other than 0x01,
   lengths 129..255 also trigger. Probe: `02 C8` (type 2, len 200) exits 134
   with stack-buffer-overflow in `main tlv_parser.c:69`. This is the same
   exactness standard as R1 (the report quotes the source). Fix: reword the two
   lines without changing the line count, e.g. "Trigger: len byte > 64 that
   passes the guard: 65..128 for type 0x01 (len > 128 is rejected), 65..255
   for any other type." Then, as in R3, re-capture the fixture or update its
   header sha256, confirm `:69`, and re-run `test_fixture_not_stale` and the
   tlv tests (fast and slow).

Non-blocking items (ticket text, for the req-engineer, best done in the same
pass):
- N4. Goal line 14, "a length over 64 overflows", predates the guard and is
  false for type 0x01 with len > 128. It is narrative, not an AC, and the
  guarding-branch AC does not list it. But the report may quote it, so align it
  with the restated ACs.
- N5. Technical notes, "Methodology flag": "about half of random second bytes
  trigger it" is stale. For S0 (type 0x01) it is 64/256 = 1/4, and the measured
  sweep shows 64 crashing values. The flag also still says "Not decided here",
  although the Log records it as resolved in favour of a guard. Mark it resolved
  or update it.
- N1 to N3 from bounce 1 still stand.

## Narrow re-review (reviewer, 2026-11-15)
Scope: R5, N4 and N5 only, under the lead's one-off exception (Log, 2026-11-15).
Verdict: **approved -> testing**. Nothing new found.

- R5, pass. `tlv_parser.c:13-14` now gives type 0x01 with len 65..128, any other
  type with 65..255, and says 0x01 with len > 128 is rejected by the guard at
  `:65`. This matches `:65` (guard), `:66` (`len > 64`) and `:69` (memcpy).
  The file is still 79 lines. `shasum -a 256` gives `6c215890...e3aa`, which
  equals the fixture header. The fixture shows `#1 main tlv_parser.c:69`, and
  SUMMARY reads `:69 in main`. `bin/tlv_parser` (08:06:37) is newer than
  `tlv_parser.c` (08:06:36), and its mtime did not change during my runs. I did
  not run `make`. Executor probes: 015041424344, 02c8, 0180, 02ff and 0241 crash
  with crash_site `main`. 019041424344, 0181 and 0240 are clean.
- N4, pass. The Goal line states the guard and both trigger ranges, matching the
  source and the probes.
- N5, pass. The Methodology flag now says 1/4 (64 of 256 values, 65..128) for S0,
  matching the earlier sweep, and is marked resolved (guarded branch, human
  decision 2026-11-07).
- Gates: I ran `pgrep` first and waited for the AFL-016 run to finish. Fast tlv
  tests: 6 passed, 1 deselected. Slow tlv test: 1 passed (93 s). `ruff check .`
  is clean, and `mypy src` reports no issues.

## Test (tester, 2026-11-15)
Verdict: **PASS**. Ready for the crew-lead to close. The ticket stays in testing.

Clean checkout: I did not use a worktree or clone. I rsync-copied the working tree to
a scratch directory outside the repo, leaving out `.venv`,
`targets/bin` and `results`. I deleted the copied `.pytest_cache`, `.mypy_cache`,
`.ruff_cache`, `.coverage` and `__pycache__`, and the copy had no `targets/bin`.
`make -C targets` in the copy built all four targets from scratch with Homebrew
clang and `-O0 -fno-omit-frame-pointer -fsanitize=address
-fsanitize-coverage=trace-pc-guard`. I ran the tests with the repo's
`.venv/bin/python -m pytest --rootdir=<copy> -p no:cacheprovider --no-cov`. The probe
confirmed that `fuzzer` was imported from the copy's `src`. After the tests, every
AFL-010 file in the copy was byte-identical (`cmp`) to the repo: tlv_parser.c (sha256
6c215890...e3aa), S0, test_tlv_parser.py, test_toy_parser.py, the fixture,
triggers.json, ground_truth.json, SHA256SUMS and Makefile. Before every make and pytest
run I checked `pgrep` and waited for the AFL-016 reviewer's runs to finish.

Gates (copy): fast `test_tlv_parser.py` + `test_toy_parser.py` gave 11 passed, 2
deselected. `-m slow` on the same files gave 2 passed (201.8 s). `ruff check .`: all
checks passed. `mypy src`: no issues in 8 files.

Per AC (my own Executor probes, script `afl010-probe.py`, independent of the tests):
- Build: pass. The copy's make output shows the flags above for `bin/tlv_parser`.
  AFL-010 changes nothing in `Makefile`; the only Makefile diff is AFL-016's
  `mini_format`.
- Bug documented: pass. `:11-24` give location, trigger, report and guard sides. The
  trigger text is exact: over all 2-byte inputs with type in {00, 01, 02, 7E, FF}
  and len 0..255 (1280 runs), the outcome is crash-at-`main` iff `len > 64 and
  not (type == 0x01 and len > 128)`. 0 mismatches, 0 hangs.
- Triggering input: pass. T1 `015041424344` is a stack-buffer-overflow WRITE of size
  80: `#0 __asan_memcpy`, `#1 main tlv_parser.c:69`, SUMMARY `:69 in main`.
- Benign: pass. `b""`, `01`, S0 and `019041424344` (rejected) give clean, exit 0, no
  "AddressSanitizer".
- FR-2 under ADR-0002: pass. T1 and S3 each give `outcome == "crash"`, signal 6
  (SIGABRT).
- stdin only (NFR-6): pass. A grep for fopen, socket, getenv, system, exec*, popen
  and connect finds nothing. The only I/O is fread(stdin) and printf.
- Guarding branch: (a) pass, since T1 edges minus S0 and REJECTED edges is non-empty
  (test); (b) pass, `:19-22`; (c) pass, one memcpy (`:69`).
- Two planted bugs: pass. `parse_ext` is not `main` and has one crash site (`:49`).
  The banned-form grep with AFL-030's 18 patterns over comment-stripped code finds 0
  hits. The local `BANNED` list is identical to the one in
  `tests/test_target_static_check.py` (AFL-030, uncommitted). `/` and `%` appear
  only in comments and the printf format string, and there is no integer divide.
- Seed: pass. S0 = `01 04 41 42 43 44` (6 bytes), clean, and the only file in
  `seeds/tlv_parser/`.
- Seed hash: pass. sha256(S0) = `0a00d89f...63be`, which matches the
  `tlv_parser/S0` line (two-space `sha256sum` format). The toy line is unchanged.
- tlv-1 shallow: pass (T1 differs from S0 at byte 1 only).
- tlv-2 deep: pass. Staircase S0 -> S1 new edges {10,12,13}, S1 -> S2 {15}, S2 -> S3
  {16}. S0, S1 and S2 are clean. S3 is a heap-buffer-overflow READ, SIGABRT,
  crash_site `parse_ext`. The documented trigger "index byte >= 4" is exact: over
  index 0..255, 0..3 are clean and 4..255 crash at `parse_ext` (252), with 03 clean
  and 04 crashing. The rationale probes hold: `01007e425844` crashes at
  `parse_ext`, `01007e424344` is clean.
- No undocumented crashes or hangs: pass. Sweep of 1536 runs: 1472 clean, 64 crash,
  all at byte 1 and all at `main`. 0 at `parse_ext`, 0 hangs (N2 counts confirmed).
- Ground truth: pass. `tlv-1` maps to main and `tlv-2` to parse_ext, both with
  target tlv_parser and file tlv_parser.c. The toy entries are unchanged.
- Retuning and freeze: n/a until AFL-011's pilot. The pointer AC is present.
- AFL-007 fixture: pass. The header sha256 equals the current source. The fixture
  has `#1 main tlv_parser.c:69`. I re-did `test_fixture_not_stale`'s logic against
  the fresh build: input `41 64 x*100` crashes, and crash_site is `main`, the same
  as the fixture's. I did not run `test_fuzzer.py` itself, which is outside my scope.
- Trigger entries: pass. `tlv-1 = 015041424344` (T1) and `tlv-2 =
  0104414243447e025810` (S3) are lowercase hex. Each crashes with crash_site equal
  to its ground_truth function, and I read the function from the file. 5/5 runs
  each were deterministic.
- `test_toy_parser.py` filter: pass. Non-toy entries are skipped, and `toy-1` and
  `toy-2` are still indexed directly.

Mutation sanity (copies under `.../tmp/afl010-mut/M*`, each built by the test
fixture's make; the repo was untouched). All 5 mutants were killed:
- M1 `field[64]` -> `field[256]` (tlv-1 removed): trigger_table, benign_and_guard_sides
  and tlv1_shallow fail.
- M2 `malloc(4)` -> `malloc(256)` (tlv-2 removed): trigger_table and
  tlv2_deep_staircase fail.
- M3 guard `len > 128` -> `len > 64` (tlv-1 unreachable for type 01): 3 fast tests
  fail. Slow: the sweep fails with `'main' in {}`.
- M4 `if (in[0] == 0x02) parse_ext("X\x10", 2)` in main (tlv-2 made shallow): the
  fast tests pass, as expected. Slow: the sweep fails with `'parse_ext' not in
  {'parse_ext': 1, 'main': 64}`.
- M5 `if (p[1] == 0xFF) abort();` in parse_ext: the banned-forms test fails. The
  staircase test also fails (see F2).

Non-blocking follow-ups:
- F1 (commit staging, orchestrator/human). The shared files `ground_truth.json`,
  `triggers.json` and `seeds/SHA256SUMS` also hold AFL-016's uncommitted `mfp-*` /
  `mini_format` lines, and the `Makefile` diff is AFL-016's alone. AFL-010's commit
  needs hunk-level staging, or a commit that is explicitly joint with AFL-016.
- F2 (fragility, informational). In M5, the crashing S3 run recorded no new edge
  over S2. Its blocks were a subset of S2's: SanitizerCoverage's default block
  pruning dropped the guard of the block holding the read, once that block gained a
  branch. The shipped source is fine (S3 adds edge 16), and the test catches the
  regression. But any future edit that adds a branch after `:49` breaks the last
  staircase step. This applies to every target whose staircase ends in a crashing
  run (AFL-016 too).
- F3. N1 (a dedup `main` mapping across targets, AFL-013/AFL-011) and N3
  (reachability of tlv-2, AFL-011 pilot) still stand. They are out of scope here.

## Follow-ups (crew-lead, 2026-11-15; non-blocking, become new tickets later)
- F1. The shared files `ground_truth.json`, `triggers.json`, `seeds/SHA256SUMS` (and
  the `Makefile`, AFL-016 only) need hunk-level staging with AFL-016, or a commit
  explicitly joint with AFL-016.
- F2. SanitizerCoverage block pruning makes a crash-ending staircase step fragile if a
  branch is added after the crash line (`tlv_parser.c:49`; applies to AFL-016 too).
- F3. Reviewer N1 (dedup `main` mapping across targets) and N3 (tlv-2 reachability)
  are deferred to AFL-013 and AFL-011.
- F4. The local `BANNED` copy in `tests/test_tlv_parser.py` is to be removed under
  AFL-030, since the list is kept in AFL-030 only.

## Log
- 2026-11-07 — created (req-engineer)
- 2026-11-07 — added guarding-branch AC and known-limitation fallback per human
  decision; the architect's methodology flag is resolved in favour of a guard
  (req-engineer)
- 2026-11-07 — resolved the number-of-bugs question (human decision: ≥2 bugs per
  target, PRD §8). `tlv-1` is classed shallow. Added ACs for a deep `tlv-2` (not in
  `main`), a shipped seed, the single-byte sweep and ground truth. Title is now
  plural. Added an open question on extending the AFL-016 retuning rule
  (req-engineer)
- 2026-11-07 — per human decisions: depends_on = [AFL-003]. Added a Retuning and
  freeze pointer AC to AFL-011's canonical rule. Resolved the retune-for-tlv-2
  question (req-engineer)
- 2026-11-07 — per human decision: Seed AC pins `S0` at
  `targets/seeds/tlv_parser/S0`, the sole initial corpus and the file all depth
  measurements use (req-engineer)
- 2026-11-07 — added S0 integrity pre-flight AC (human decision) (req-engineer)
- 2026-11-07 — review fix: added AC to re-capture AFL-007's tests/fixtures/ tlv_parser report and update its recorded source commit if the overflow report changes (human decision) (req-engineer)
- 2026-11-12 — Test approach: tester runs `pytest -m slow` (the S0 depth sweeps, excluded from the default run) as a required step (human decision) (req-engineer)
- 2026-11-12 — Technical notes: tests use AFL-007's `seed_files` and `crash_site` from the start, per AFL-029 (human decision, 2026-11-12) (req-engineer)
- 2026-11-12 — added AC "Symbolizer-check trigger entries": `tlv-1` and `tlv-2` each get one known-crashing input in AFL-011's `targets/triggers.json`, tested to give `crash_site()` equal to its `ground_truth.json` function, for AFL-011's per-bug pre-flight symbolizer check (human decision, 2026-11-12) (req-engineer)
- 2026-11-14 — extended the "Two planted bugs" AC: `tlv-2` is ASan-reported with a stack at a target function, is not an integer divide by zero (no trap on arm64), and the source passes AFL-030's static source check (list kept in AFL-030 only) (from AFL-030 condition-1 evidence, 2026-11-14) (req-engineer)
- 2026-11-14 — developer: implemented. tlv-1 (shallow, main, memcpy; guard type==1 && len>128; T1 = S0 with byte 1 -> 0x50) and tlv-2 (deep, parse_ext, heap read table[p[1]]; staircase S0 -> +7E 00 -> +7E 01 58 -> +7E 02 58 10). S0 = 01 04 41 42 43 44, hash in seeds/SHA256SUMS, targets/triggers.json created with tlv entries. tests/test_tlv_parser.py (7 tests incl. slow sweep, static banned-form check). Known follow-ups: tests/fixtures/tlv_parser_asan_memcpy.txt needs re-capture (report line changed; out of my write scope) and tests/test_toy_parser.py::test_ground_truth_and_source_docs iterates all ground-truth entries and now fails on tlv entries (needs filter to "toy-" keys; out of scope). Retuning/freeze: n/a yet.
- 2026-11-14 — developer: scope extension (orchestrator). tests/test_toy_parser.py::test_ground_truth_and_source_docs now skips non-toy_parser ground-truth entries (toy-1/toy-2 still asserted present); tests/fixtures/tlv_parser_asan_memcpy.txt re-captured from the new build with the tlv-1 trigger 015041424344 (header names input hex, AFL-010 uncommitted source and its sha256; frame #0 __asan_memcpy above #1 main tlv_parser.c:69). Files changed additionally: tests/test_toy_parser.py, tests/fixtures/tlv_parser_asan_memcpy.txt.
- 2026-11-14 — reviewer: changes requested (bounce 1). R1 tlv-2 trigger index >= 4 not >= 16 (tlv_parser.c:28); R2 depth rationale false, the index byte is not absent from S0 (:31); R3 fixture sha256 re-capture after the source edit; R4 update the earlier ACs and Technical notes to match the guard. All behavioural ACs measured passing; N1 dedup `main` mapping across targets flagged to AFL-013/AFL-011. Status in-progress (reviewer)
- 2026-11-14 — developer: review bounce 1 R1-R3 fixed (tlv_parser.c comments only: index byte >= 4, depth rationale reworded, line count unchanged so memcpy stays at :69 and parse_ext crash at :49; fixture re-captured with new sha256 d8e6d92e...); R4 (ticket AC and technical-notes text) pending with the req-engineer.
- 2026-11-14 — req-engineer: R4 fixed (ACs "planted bug is documented" and "A known triggering input" now state the guard from tlv_parser.c:65-69: overflow iff in[1] > 64 and not (in[0] == 0x01 && in[1] > 128), so type 0x01 triggers only with 65..128, and 2 bytes suffice; Technical notes: frame `main tlv_parser.c:69` (was :19), overflow claim restricted to inputs passing the guard, trigger replaced by T1 = 015041424344 with the rejected-by-guard 01 90 ... added to the benign list; checkbox states unchanged). Status in-progress (req-engineer)
- 2026-11-14 — reviewer: re-review after bounce 1: R1-R4 verified fixed (index >= 4 boundary 03/04 probed; fixture sha256 d8e6d92e matches, frame #1 main :69; gates green, fast 50 passed, slow 1 passed). Changes requested (bounce 2): R5 tlv_parser.c:13 tlv-1 trigger "65..128" omits that any non-0x01 type triggers for 65..255 (02 C8 crashes at main :69), short of the restated AC; R5 needs a fixture re-capture as in R3. N4 Goal line and N5 stale methodology flag (ticket text). Second bounce: stop condition, human decision needed. Status in-progress (reviewer)
- 2026-11-15 — lead decision, 2026-11-14: one-off exception to the stop-after-two-bounces rule (CLAUDE.md §7 stop condition 3) — after bounce 2 (R5, a source comment only; program correct, every functional check passed), one targeted fix plus a narrow re-review covering only R5, N4 and N5; if that re-review finds anything new it stops and reports to the lead; no third full round. (orchestrator, recorded by req-engineer)
- 2026-11-15 — req-engineer: N4 (Goal line) and N5 (Methodology flag: 1/4, resolved: guarded branch) fixed. Status in-progress (req-engineer)
- 2026-11-15 — reviewer: narrow re-review (R5, N4, N5 only, per lead exception) passed; R5 comment exact vs :65-69, fixture sha256 6c215890 matches, frame main :69, 79 lines, binary newer than source; N4 and N5 accurate; tlv fast 6 passed, slow 1 passed, ruff/mypy clean. Approved -> testing (reviewer)
- 2026-11-15 — tester: PASS on a clean copy (rsync, no .venv/bin/results; fresh make): fast 11 passed, slow 2 passed (201.8 s), ruff/mypy clean; independent probes confirm the tlv-1 trigger range (1280 2-byte inputs, 0 mismatches), the tlv-2 index boundary 03/04, the staircase edges, the sweep (64 crashes at main byte 1, 0 at parse_ext, 0 hangs), the S0 hash, triggers vs ground truth and the fixture sha; mutation sanity 5/5 killed (M4 by the slow sweep only); F1 shared-file hunk staging with AFL-016, F2 SanCov pruning fragility of the last staircase step. Left in testing for the crew-lead to close (tester)
- 2026-11-15 — DoD verified, closed (crew-lead): every AC evidenced in the tester's section (Fallback moot, guard accepted 2026-11-07; Retuning and freeze n/a until AFL-011's pilot); reviewer approved via the narrow re-review (lead decision, 2026-11-14, option 1); tester PASS on a clean copy; R1-R5 fixed, N2/N4/N5 done; follow-ups F1-F4 above (F1 hunk staging with AFL-016, F2 SanCov pruning fragility, F3 N1/N3 to AFL-013/AFL-011, F4 remove local BANNED copy under AFL-030). Commit with the AFL-010 id is the human's. testing → done (crew-lead)
- 2026-11-15 — retuned (AFL-035): tlv-2 (parse_ext) retuned once under the pre-registered retuning rule; first pilot (run on d9a22db, results/pilot/first_pilot, seeds 2000..2002, 3 trials per target x arm, c = 3; found = a crash_events.csv row whose crash_site equals the bug's ground_truth function): tlv-2 uniform 0/3, fast 0/3 -> (i) never found = yes, (ii) no; staircase, S0, odds and sweeps are in AFL-035's Log (developer)
