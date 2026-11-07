---
id: AFL-010
title: tlv_parser target + documented bugs
requirement: SC1
paper_ref: Klees § performance measures / ground truth (known bugs as ground truth)
module: targets/tlv_parser.c
depends_on: [AFL-003]
status: backlog
owner: developer
---

## Goal
A more realistic target: a Type-Length-Value parser that trusts its length byte,
so a length over 64 overflows a 64-byte stack buffer and AddressSanitizer catches
it. This is ground truth for SC1 and for time-to-first-crash (PRD §8).

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
      into `field`), its trigger (length byte > 64) and the expected ASan report
      (stack-buffer-overflow).
- [ ] A known triggering input on stdin (length byte > 64 followed by enough
      bytes) produces an ASan stack-buffer-overflow report.
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
      expected ASan report and depth class.
- [ ] **Seed.** A seed input `S0` (≤ 32 bytes, `outcome == "clean"`) is committed
      as this target's initial corpus, at the same location AFL-016 uses for
      per-target seeds.
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

## Technical notes (architect)
- **Expected report:** an ASan `stack-buffer-overflow` WRITE inside the memcpy
  interceptor (`__asan_memcpy`), with the next frame at `main tlv_parser.c:19`. Under
  `ASAN_OPTIONS=abort_on_error=1` (AFL-003, → `docs/adr/0002-asan-configuration.md`,
  accepted 2026-11-07) the process ends with SIGABRT, a crash under FR-2 as written.
  ADR-0002's "What AFL-010 relies on" section is the "agreed ASan configuration"
  the AC refers to.
- **Trigger:** `b"\x01\x50" + b"A" * 80` (length 80). Benign: `b"\x01\x04ABCD"`
  and `b""` exit 0.
- The overflow fires for any `in[1] > 64` whatever the real input length, because
  memcpy reads from the 512-byte `in` buffer. So a trigger needs only 2 bytes.
- Add ground-truth entry `tlv-1` (`function: main`, `file: tlv_parser.c`) to
  `targets/ground_truth.json`, as in AFL-009.
- `printf` writes to stdout. The executor discards stdout, so no change is needed.
- Same Makefile changes as AFL-009: `-fno-omit-frame-pointer` and the coverage runtime.
- **Methodology flag (needs Vision/PRD decision):** this bug is one mutation away
  from any 2-byte seed, since about half of random second bytes trigger it. Both arms
  will probably find it within seconds, so TTFC will not separate the schedules. If
  Vision wants a target that discriminates, gate the overflow behind deeper checks
  (e.g. a type check plus a magic header). Not decided here.

## Test approach (tester)
Build, run the trigger and benign inputs, and assert the ASan report or clean
exit. Check the trigger's classification through the executor once AFL-003 lands.

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
