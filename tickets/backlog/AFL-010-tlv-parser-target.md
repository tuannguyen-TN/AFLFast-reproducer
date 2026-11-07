---
id: AFL-010
title: tlv_parser target + documented bug
requirement: SC1
paper_ref: Klees § performance measures / ground truth (known bugs as ground truth)
module: targets/tlv_parser.c
depends_on: []
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
