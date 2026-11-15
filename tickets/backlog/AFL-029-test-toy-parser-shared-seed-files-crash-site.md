---
id: AFL-029
title: test_toy_parser uses AFL-007's shared seed_files and crash_site
requirement: SC1 / PRD §8 (AFL-009 depth claims), FR-6 (AFL-013 crash-site dedup)
paper_ref: Klees § performance measures / ground truth (known bugs as ground truth; crash de-duplication)
module: tests/test_toy_parser.py
depends_on: [AFL-007, AFL-009]
status: backlog
owner: developer
---

## Goal
`tests/test_toy_parser.py` has its own copy of two rules that AFL-007 defines once
in `src/fuzzer/fuzzer.py`: which files in a seeds dir are seeds, and what "the
crash site" is. This ticket replaces both copies with AFL-007's functions (human
decision, 2026-11-12). Then the AFL-009 depth claims are measured with the same
site definition that the campaign's crash-event stream and AFL-013's dedup use,
and the seed check agrees with AFL-011's pre-flight.

## Acceptance criteria
- [ ] **(a) Seed listing (human decision, 2026-11-12).** The test that asserts
      `list((TARGETS / "seeds/toy_parser").iterdir()) == [S0]` (today
      `test_seed_and_hash`) uses `fuzzer.fuzzer.seed_files()` instead, and
      asserts that the names it returns are exactly `["S0"]`. This is the same
      seed set AFL-011's pre-flight requires (exactly `{S0}` among non-hidden
      regular files). So a Finder-written `.DS_Store` in
      `targets/seeds/toy_parser/` no longer fails the test. Tests, each on a
      temporary copy of `targets/seeds/toy_parser/` (never the real dir):
      (i) with an added `.DS_Store`, the assertion still holds;
      (ii) with an added non-hidden file `S1`, the assertion fails.
- [ ] **(b) Crash site (human decision, 2026-11-12).** The file's local `site()`
      function and its regex are deleted, and `re` is no longer imported unless
      another use remains. Every site check in the file (`test_toy1_deep`,
      `test_toy2_shallow`, `test_single_byte_sweep`) calls
      `fuzzer.fuzzer.crash_site(r.stderr, "toy_parser.c")`. The two bug sites
      stay distinct: `toy-1` is asserted at `check` and `toy-2` at `scan`, and
      the sweep still asserts that every crash site is `check` or `scan` and
      that `scan` occurs and `check` does not. Check: `grep -n "def site"
      tests/test_toy_parser.py` prints nothing.
- [ ] **(c) Binding note for the other targets (human decision, 2026-11-12).**
      The Technical notes of AFL-010 and AFL-016 each contain one line saying
      that the target's tests use `seed_files` and `crash_site` from
      `fuzzer.fuzzer` from the start (no local copies). Written by the
      req-engineer on 2026-11-12 together with this ticket; check that both
      lines are present.
- [ ] **(d) Gates.** `ruff check .`, `mypy src`, `pytest` and `pytest -m slow`
      all exit 0, and `cd targets/seeds && shasum -a 256 -c SHA256SUMS` reports
      `OK` for `toy_parser/S0`. No file under `targets/`, `src/` or `docs/` is
      changed by this ticket.

## Technical notes (architect)
- Interfaces, from AFL-007 (`src/fuzzer/fuzzer.py`), not changed here:
  - `seed_files(seeds_dir: Path) -> list[Path]`: regular files whose names do
    not start with `.`, sorted by name. May return `[]`.
  - `crash_site(stderr: bytes, source: str) -> str`: the function name of the
    first ASan frame located in `source`, skipping runtime/interceptor and libc
    frames. It never returns `""`. Its sentinels are `"no_stack"`,
    `"unsymbolized"` and `"no_target_frame"`.
- A sentinel is not `check` or `scan`, so the sweep's assertion (every crash
  site is `check` or `scan`) fails on one. Keep it that way, because a sentinel
  in the sweep is an undocumented crash.
- For AC (a), a small helper that takes a seeds dir and makes the assertion
  lets the real-dir test and the two temp-copy tests share one assertion.
- Off the critical path. Not in the AFL-011 freeze set (req-engineer judgement,
  2026-11-12, see INDEX). If it is worked, it lands before AFL-011 checklist
  item (b) (`pytest -m slow`) runs, so (b)'s evidence covers the changed sweep.
  If it lands after (b) has run, (b) is re-run before the freeze commit.

## Test approach (tester)
Run `pytest` and `pytest -m slow` (the sweep uses `crash_site` now). Grep that
`def site` is gone and that `crash_site` and `seed_files` are imported from
`fuzzer.fuzzer`. Mutant check for (a): replace `seed_files(...)` with
`iterdir()` in the helper and confirm test (i) fails. Mutant check for (b):
make the `toy-2` assertion expect `check` and confirm `test_toy2_shallow` fails.
Run `shasum -a 256 -c` on `targets/seeds/SHA256SUMS`.

## Log
- 2026-11-12 — created from human decisions of 2026-11-12: use AFL-007's
  `seed_files` and `crash_site` in tests/test_toy_parser.py; binding note added
  to AFL-010 and AFL-016 Technical notes (human decision, 2026-11-12)
  (req-engineer)
