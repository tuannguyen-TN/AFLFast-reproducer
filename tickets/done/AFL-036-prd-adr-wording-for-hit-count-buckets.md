---
id: AFL-036
title: PRD and ADR wording for hit-count buckets (follow-up to AFL-034)
requirement: FR-1 / FR-3 / FR-5
paper_ref: AFLFast / ADR-0001 (coverage note: hit-count buckets, amendment of 2026-11-15)
module: docs/PRD.md, docs/adr/0004-*.md, docs/adr/0005-*.md, tickets/done/AFL-034-hit-count-bucket-coverage.md
depends_on: [AFL-034]
status: done                       # backlog|in-progress|review|testing|done
owner: req-engineer                   # the drafting is Opus
---

## Goal
After AFL-034 the code retains on (edge, bucket) pairs, but PRD §8 and two ADRs
still describe presence-only edge sets. Bring the text into line with ADR-0001's
amendment of 2026-11-15, without changing any measured quantity. Part of the
AFL-011 freeze set (checklist item (a)). Pre-registration-adjacent text: the human
reads the staged diff before the commit.

## Acceptance criteria
- [x] **PRD §8 deviation (iv).** docs/PRD.md §8 deviation (iv) (around lines 185-200;
      today it says "presence-only retention keeps a subset of what AFL's hit-count
      bucketing keeps, so our corpus tends to reach 10 seeds later") is updated to
      state that coverage uses AFL hit-count buckets (1, 2, 3, 4-7, 8-15, 16-31,
      32-127, 128+) for retention, `path_id` and f(i) (AFL-034; ADR-0001 amendment of
      2026-11-15). Any remaining §8 coverage wording that implies plain edge-set
      retention is updated the same way (check: grep §8 for "presence", "edge set",
      "subset" and read each hit). The primary coverage measure stays "final edges"
      (distinct edge ids), stated unchanged. The wording follows
      docs/adr/0001-coverage-mechanism.md (amendment and addendum) and
      tickets/done/AFL-034-hit-count-bucket-coverage.md; it adds no claim they do not make.
- [x] **ADR-0004 §2 and ADR-0005 §6 notes.** Each gets a dated note, "superseded by
      the ADR-0001 amendment of 2026-11-15", with one line on what changed
      (ADR-0004 §2: "over the presence edge set" is now over (edge, bucket) pairs;
      ADR-0005 §6: `path_id` hashes pairs, so `distinct_path_ids` counts distinct
      (edge, bucket) sets, while `edges` / `final_edges` stay distinct edge ids). Added
      without rewriting the existing text (`git diff` shows additions only in both).
- [x] **AFL-034 correction.** A correction Log line is appended to the closed ticket
      tickets/done/AFL-034-hit-count-bucket-coverage.md. Its developer Log line
      (around line 163) says "the Makefile bin rule does not depend on cov_rt.c";
      that is wrong: targets/Makefile has `$(BIN)/%: %.c cov_rt.c` (the reviewer
      confirmed this; a same-second mtime caused the stale build). Log append only; no
      other line of the closed ticket changes.
- [x] **Item (c) recorded.** This ticket's Log records that the tests/test_cli.py stub
      change in AFL-034 was forced by the type change (`ExecResult.edges` to `hits`)
      and was accepted by the lead on 2026-11-16.
- [x] **No data-affecting change.** `git diff` of this ticket's files (the `module:` list)
      touches no file under src/, harness/, targets/ or tests/ (the harness/ and tests/
      changes in the working tree are AFL-037's and are staged separately); docs/PRD.md
      changes are confined to §8 deviation (iv) and the §6 FR-1 and FR-3
      acceptance-criteria cells.
- [x] **No paths.** No home, scratch or temp path in any touched file (a grep for
      home, job-scratch and temp-directory prefixes finds nothing in the added lines).
- [x] FR-1/FR-3 wording (scope extension by the orchestrator, 2026-11-16; approved by the lead, lead decision, 2026-11-16)

## Technical notes (architect)
- Docs-only. ADR-0001 stays the authority; ADR-0004 and ADR-0005 get pointer notes, not rewrites.
- Hazard: PRD §8 is pre-registered text. Keep edits to the coverage wording named above.

## Test approach (tester)
Diff review of added lines only; grep checks named in the ACs; confirm every claim in the
new §8 wording appears in ADR-0001's amendment or AFL-034. No code gates are needed
beyond the hooks.

## Review notes (reviewer, 2026-11-16, round 1)
Verdict: **BOUNCE** (3 must-fix). Checked against docs/adr/0001-coverage-mechanism.md
(amendment and addendum of 2026-11-15), src/fuzzer/coverage.py, corpus.py, fuzzer.py,
executor.py, targets/cov_rt.c, targets/Makefile, not against this ticket's Log.

Verified (per AC):
- PRD §8 (iv): `BUCKET_LUT` gives 1, 2, 3, 4-7, 8-15, 16-31, 32-127, 128-255, as stated;
  cov_rt.c saturates at 255 (`v + (v != 255)`); retention is `has_new_edges(result.hits,
  seen_hits)`; `path_id(r.hits)` at all four loop sites and in `observe()`, so f(i) is
  over pairs; `edges` is `len(corpus.seen)`, distinct edge ids of clean executions. The
  claims about AFL 2.x wrapping and pre-switch data not being comparable are in the ADR-0001
  addendum and amendment. Grep of §8 for "presence", "edge set", "subset": only (iv).
  No hypothesis, test, family, endpoint or other rule changed in meaning; the old (iv)
  sentence was a disclosure, not a rule.
- ADR-0004 §2 / ADR-0005 §6: `git diff --numstat` gives 14/0 and 12/0 (additions only).
  ADR-0004's 1:1 argument is correct over pairs: every clean execution goes through
  `observe()` (S0 and the loop), so `seen_hits` is the union of the pairs of all earlier
  clean executions. A retained input has a pair outside it and so differs from every earlier
  seed. Checked with a stub run of `observe()`: an input with the same edge ids and a new
  bucket is retained, `seen` stays {1, 2}, and a repeat raises the first seed's `path_freq` to 2.
- AFL-034: 1/0 numstat, one appended line; the line it corrects (163) is the developer's
  bounce-round-1 line; Makefile line 21 is `$(BIN)/%: %.c cov_rt.c | $(BIN)`.
- Item (c): recorded in the Log.
- No paths: grep of added lines (home, temp, scratch, var/folders, TMPDIR) finds nothing.
- FR-1/FR-3 (scope extension): FR-3 is accurate. On FR-1, see S1.

Must-fix:
- **M1 (AC "No data-affecting change", ticket text).** As written, the AC is not met:
  docs/PRD.md also changes §6 FR-1/FR-3, and a repo-wide `git diff` does touch harness/
  and tests/ (AFL-037's work in the same tree). Replace the AC text with: "`git diff`
  of this ticket's files (the `module:` list) touches no file under src/, harness/,
  targets/ or tests/ (the harness/ and tests/ changes in the working tree are AFL-037's
  and are staged separately); docs/PRD.md changes are confined to §8 deviation (iv)
  and the §6 FR-1 and FR-3 acceptance-criteria cells." Also leave the FR-1/FR-3 box
  unchecked until the lead approves it at stop 5, and log that decision with its date.
- **M2 (ADR-0005 §6 note; stale text that contradicts corpus.py).** The "Why" bullet
  (line ~326) says `seen` "is also the set that retention already keeps, so no second
  coverage set is needed". That is now false: retention keeps `seen_hits`. The note
  also says the "presence only" wording is the pre-switch record. But that bullet's
  "`edges` counts trace-pc-guard ids, presence only" is still true. Replace the note's
  clause "; the "presence only" wording above is the pre-switch record." with: ". In the
  "Remaining difference from AFL" bullet, `edges` still counts trace-pc-guard ids,
  presence only; retention, `path_id` and f(i) now use hit-count buckets as AFL does,
  so the remaining differences there are guard ids instead of hashed (previous, current)
  location pairs, and counters that saturate at 255 instead of wrapping (ADR-0001
  amendment). In the "Why" bullet, `seen` is no longer the set that retention keeps:
  retention keeps `corpus.seen_hits`, and `seen` is a second set, of edge ids, kept for
  `edges` and updated in the same `observe()` step."
- **M3 (ADR-0005 §3 line ~158-159; replay chain premise).** The note re-reads §3's
  "Retention and f(i)" bullet over pair sets. But the link "An execution's outcome, its
  edge set and its crash stderr depend only on the input bytes" still covers only edge
  sets. So the chain no longer supports its own conclusion. The claim itself still holds:
  `Executor.run()` resets the bitmap before every execution, and only the target's guards
  increment it. Append to the note: "§3's "Each outcome is a function of the input bytes"
  link covers each execution's hit counts, and so its (edge, bucket) pair set, not only its
  edge set: `Executor.run()` resets the bitmap before every execution, and the counters
  change only through the target's own guard hits."

Should-fix:
- **S1 (PRD §6 FR-1, line 84).** "obtains the set of hit edges and can tell if any (edge,
  bucket) pair is new" names one thing obtained and another compared. Proposed: "after a
  run the fuzzer obtains the hit edges, each with its AFL hit-count bucket (the set of
  (edge, bucket) pairs), and can tell if any pair is new vs. the global seen-set" (the
  "was" note stays as is, but it should quote the whole old clause: "obtains the set of hit
  edges and can tell if any are new vs. the global seen-set").

Nits (optional, accurate as is):
- N1 ADR-0005 §6 "Crashes do not count" (line ~315): "a crash's edges only for its
  `path_id`" now means its pairs. The note's general sentence covers this.
- N2 ADR-0004 §5 (line ~187): "Because `seen` starts empty" now means `seen_hits`;
  the behaviour is unchanged (≥1 edge iff ≥1 pair). It could be named in the ADR-0004 note.
- N3 ADR-0004 §2 hang/crash bullets argue over edge sets. They stay valid over pairs (equal
  pair sets imply equal edge sets, so the crash argument only gets stronger). No change needed.

## Review notes (reviewer, 2026-11-16, round 2)
Verdict: **APPROVE -> testing.** All round-1 items verified; no new issue.
- `git diff --numstat`: PRD 15/5 (the 5 removed lines are the FR-1 and FR-3 cells and the
  three lines of the old (iv) sentence), ADR-0004 15/0, ADR-0005 21/0, AFL-034 1/0. A grep
  of the ADR and AFL-034 diffs for removed lines finds none. The path grep of added lines
  finds nothing.
- M1: AC text replaced verbatim; FR-1/FR-3 box is unticked (line 53).
- M2: the ADR-0005 §6 note now carries the "Remaining difference from AFL" and "Why"
  sentences; `corpus.py` updates `seen` and `seen_hits` in the same retention branch.
- M3: the §3 input-bytes sentence is present; `Executor.run()` calls `self._bitmap.reset()`
  first, and only `__sanitizer_cov_trace_pc_guard` writes the counters.
- S1: FR-1 reworded; the "was" note quotes the whole old clause. N2: ADR-0004 note names §5;
  "≥1 edge iff ≥1 pair" is true (a pair exists exactly when its count is nonzero).
- "as AFL does" (drafter's query): keep it; no new source needed. The project's own record
  already makes the claim. ADR-0001's original Consequences paragraph says "AFL and AFLFast
  use hit-count buckets, so loop-iteration differences count as new coverage and as distinct
  paths", and the amendment says `coverage.py` buckets "AFL's way". That is the retention
  and path-identity claim the phrase repeats. It also matches AFL 2.51b, where
  `classify_counts` runs on `trace_bits` before `has_new_bits` and before the trace is
  hashed. Optional nit only: append "(ADR-0001 Consequences, presence-only paragraph)" after
  "as AFL does" if the lead wants a pointer.
- Condition (not a defect): the FR-1/FR-3 AC waits on the lead at stop 5. If the lead
  declines, revert the two §6 cells and narrow the "No data-affecting change" AC back to §8
  (iv) before the close. The ticket must not close while that box is unticked.

## Log
- 2026-11-16 — created (req-engineer), lead decision, 2026-11-16
- 2026-11-16 — (req-engineer) drafted. PRD §8 deviation (iv): the presence-only sentence is replaced by the hit-count-bucket wording (buckets 1, 2, 3, 4-7, 8-15, 16-31, 32-127, 128+ for retention, `path_id` and f(i); saturation at 255 vs AFL 2.x wrapping; final edges stays distinct edge ids; pre-switch path ids and corpus sizes not comparable), with a dated "was" note that quotes the old sentence verbatim. Every claim is taken from the ADR-0001 amendment/addendum or AFL-034 and checked against coverage.py, corpus.py and fuzzer.py (`path_id(r.hits)`, `seen_hits`, `len(corpus.seen)`). Grep of §8 for "presence", "edge set", "subset": deviation (iv) was the only hit. ADR-0004 §2 and ADR-0005 §6: one dated pointer note each, inserted at the end of the section, no existing line changed. AFL-034: one correction Log line appended (Makefile does depend on cov_rt.c). Path grep on all five touched files: no matches. No file under src/, harness/, targets/ or tests/ touched; no shell available, so `git diff` was not run here (orchestrator to confirm). (req-engineer)
- 2026-11-16 — item (c): the tests/test_cli.py stub change in AFL-034 was forced by the type change (`ExecResult.edges` field to `hits`) and was accepted by the lead (lead decision, 2026-11-16).
- 2026-11-16 — (req-engineer) scope extension by the orchestrator, 2026-11-16; pending the lead's approval at stop 5. PRD §6 FR-1 ("can tell if any (edge, bucket) pair is new") and FR-3 ("retained iff it reveals ≥1 new (edge, bucket) pair") reworded, each with a dated "was" note quoting the old text verbatim; no other §6 change. This widens the "No data-affecting change" AC's "§8 coverage wording" clause to §6 FR-1/FR-3. The ADR-0004 §2 note now also names the §1 `Seed` comment and `observe()` steps (2)–(3), and states that the 1:1 argument holds over pairs (checked against corpus.py). The ADR-0005 §6 note now also names the "Clean executions count" bullet and §3's "functions of the clean edge sets" line, and states that `seen` stays the union of the edge ids of clean executions. Only the note text was edited; no original ADR text changed. PRD §8 targets bullet left unchanged (the documented chains add new edge ids). (req-engineer)
- 2026-11-16 — (reviewer) BOUNCE (round 1) -> in-progress. Must fix: M1 AC text (PRD scope now §8 (iv) + §6 FR-1/FR-3; git diff scoped to module files; FR-1/FR-3 box unchecked until the lead approves), M2 ADR-0005 §6 note ("Why" bullet's single-set claim; "presence only" clause), M3 ADR-0005 §3 replay-chain link over pair sets. S1 FR-1 wording. Nits N1-N3. Claims checked against code and ADR-0001 amendment; additions-only confirmed; no paths. (reviewer)
- 2026-11-16 — bounce 1 fixed (req-engineer). M1: "No data-affecting change" AC text replaced with the reviewer's wording (`git diff` scoped to the `module:` files; PRD scope §8 deviation (iv) plus §6 FR-1 and FR-3 cells); FR-1/FR-3 box unticked on 2026-11-16, stays unticked until the lead approves at stop 5. M2: ADR-0005 §6 note's "presence only ... pre-switch record" clause replaced by the reviewer's "Remaining difference from AFL" and "Why" bullet text (checked: corpus.py updates `seen` in the same retention branch as `seen_hits`). M3: ADR-0005 note gains the §3 "Each outcome is a function of the input bytes" sentence (checked: `Executor.run()` calls `self._bitmap.reset()` first; only cov_rt.c's `__sanitizer_cov_trace_pc_guard` writes the counters). S1: PRD FR-1 reworded as proposed; its "was" note quotes the whole old clause. N2: ADR-0004 note names §5's "Because `seen` starts empty" (now `seen_hits`, behaviour unchanged). N1, N3: no change. Only note text edited in both ADRs; reviewer wording used verbatim, none found inaccurate. (req-engineer)
- 2026-11-16 — (reviewer) APPROVE (round 2) -> testing. M1, M2, M3, S1, N2 verified against code and diff; ADRs and AFL-034 additions only; no paths. "as AFL does" kept (supported by ADR-0001 Consequences and amendment). Close is conditional on the lead's FR-1/FR-3 decision at stop 5. (reviewer)
- 2026-11-16 — (tester) PASS (FR-1/FR-3 AC pending lead at stop 5, not a failure). Checked independently against code: BUCKET_LUT gives 1, 2, 3, 4-7, 8-15, 16-31, 32-127, 128+ (spot-checked 1..255); cov_rt.c saturates at 255; `Executor.run()` resets the bitmap first; `Corpus.observe()` retains on `seen_hits`, updates `seen` (edge ids) in the same branch; fuzzer uses `path_id(r.hits)` and `len(corpus.seen)`; Makefile line 21 is `$(BIN)/%: %.c cov_rt.c | $(BIN)`. Stub run: same edge ids with a new bucket is retained, `seen` stays {1, 2}, `seen_hits` grows, path_id differs, a repeat is not retained. `git diff --numstat`: ADR-0004 15/0, ADR-0005 21/0, AFL-034 1/0 (additions only); PRD 15/5, and the 5 removed lines (FR-1 cell, FR-3 cell, 3 lines of the old (iv) sentence) are each quoted verbatim in a "was" note. No hypothesis, test, endpoint (final edges = distinct edge ids), D_max, stopping or dedup wording changed. Path grep of added lines in docs/ and tickets/done/: no matches. No timed run active. Gates: ruff clean; mypy src clean (8 files); pytest default suite "585 passed, 10 deselected in 108.02s". No -m slow (docs ticket). No finding. (tester)
- 2026-11-16 — the lead approved the PRD §6 FR-1 and FR-3 rewording (lead decision, 2026-11-16); FR-1/FR-3 box ticked. (orchestrator)
- 2026-11-16 — DoD verified; closed via the gated mv (crew-lead)
