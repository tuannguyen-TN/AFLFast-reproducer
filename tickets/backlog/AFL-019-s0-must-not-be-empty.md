---
id: AFL-019
title: S0 pre-flight rejects a zero-length seed (mutate(b"") can return b"")
requirement: FR-7 (S0 pre-flight), FR-3 / FR-4 (corpus never holds an empty seed), NFR-1
paper_ref: n/a (ADR-0004 §6, initial corpus = S0, no b"" fallback; AFLFast §5.1 used the empty file as its seed, a departure ADR-0004 already discloses)
module: harness/run_campaign.py (S0 pre-flight), tests/
depends_on: [AFL-011, AFL-016]
status: superseded
owner: developer
---

## Goal
`src/fuzzer/mutator.py` `mutate()` on `b""` can return `b""`: `delete_bytes` and
`splice` never empty a non-empty input, but an empty input stays empty unless a
stacked havoc operator inserts bytes, and `splice` returns `data` unchanged when
`min(len) < 2`. Every corpus entry descends from S0 (ADR-0004 §6, sole initial
corpus), and no operator turns a non-empty input into an empty one. So if S0 is
non-empty, no corpus seed is ever empty and `mutate(b"")` is unreachable. Enforce
that at the one place S0 enters the experiment: the S0 integrity pre-flight.

## Acceptance criteria
- [ ] The S0 pre-flight (AFL-011 AC "Pre-flight S0 integrity check") also rejects
      any `targets/seeds/<target>/S0` of length 0. The runner exits non-zero with
      an error that names the target and says the seed file is empty, and creates
      no trial directories. This applies to the first pilot, the confirmation pilot
      and the main campaign, with no override flag.
- [ ] A test creates a config whose target has a zero-length `S0` (with a matching
      `SHA256SUMS` line, so only the length check can fail) and asserts a non-zero
      exit, the error message naming the target, and zero trial directories.
- [ ] `src/fuzzer/mutator.py` is unchanged by this ticket (`git diff` on it is
      empty).
- [ ] The statement "non-empty S0 + no operator empties a non-empty input ⇒
      `mutate(b"")` is unreachable in a campaign" is recorded in a code comment next
      to the length check, citing this ticket.

## Technical notes (architect)
- The pre-flight is an AC of AFL-011 (added by commit 6ec473c as ticket text; not
  yet implemented). This ticket extends it. If AFL-011 is still open when this is
  pulled, it may be implemented in the same change as AFL-011's pre-flight, with
  both ticket ids in the commit message.
- Covers every target's S0 (AFL-009, AFL-010, AFL-016), not just the mini format
  parser. The depends_on lists AFL-016 because its Seed AC is the most recent S0
  definition; AFL-011 already depends on AFL-009/010/016.
- Out of scope: the single-run CLI `--seeds DIR` path (AFL-008) does not go through
  the campaign pre-flight. Not required for the experiment; file a ticket if wanted.
- AFL-016's "empty input" in its path-diversity set is a benign test input, not a
  seed. It is unaffected.

## Test approach (tester)
Run the new pre-flight test (empty S0 → abort, no trial dirs). Confirm the existing
pre-flight tests (missing S0, tampered S0, missing `SHA256SUMS` entry) still pass.
Check `git diff -- src/fuzzer/mutator.py` is empty and the reachability comment
exists.

## Log
- 2026-11-07 — created (req-engineer) from AFL-005 close follow-ups (human decision)
- 2026-11-07 — batch grooming: folded into AFL-011 (ACs appended to AFL-011's S0 pre-flight AC block); status superseded, work tracked under AFL-011 (human decision) (req-engineer)
