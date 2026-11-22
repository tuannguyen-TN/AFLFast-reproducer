---
id: AFL-040
title: Condense REPORT.md
requirement: G5, NFR-1 (final report); lead decision, 2026-11-21
paper_ref: n/a
module: docs/report/REPORT.md, docs/report/DETAILS.md
depends_on: [AFL-039]
status: done
owner: orchestrator (report text; lead decision, 2026-11-17)
---

## Goal
Make the main report readable in about 15 minutes. `docs/report/REPORT.md` becomes a
condensed report of at most 3,500 words; every passage removed from it is kept in a new
`docs/report/DETAILS.md`, so nothing leaves the record (lead decision, 2026-11-21).

## Acceptance criteria
- [x] `docs/report/REPORT.md` has at most 3,500 words by `wc -w`, including tables and
      excluding the References section; the count is recorded in the Log.
- [x] REPORT.md keeps section numbers 1–8 and the §4.1 heading; References is its last section.
- [x] Section content and budgets as in the lead decision: §1 (~300) with §1.1 input and
      output (~150); §2 (~300); §3 (~450) with the six-row targets table and three to five
      deviation bullets; §4 (~900): §4.1 every role item one line each, §4.2 a 14-row phase
      table, §4.3 the challenges table with one-sentence cells, §4.4 the count (19) and a
      decision | chosen | alternative table, §4.5 both code-size tables and authorship in
      three sentences; §5 (~350); §6 (~450) with the primary table, the `tlv_parser`
      coverage figure, one paragraph on mfp-2 and one line on throughput; §7 (~300) one
      line per threat; §8 (~200). Appendix A moves to DETAILS.md, with one pointer line in
      REPORT.md to it and to the README.
- [x] No new claims and no changed numbers: every sentence in REPORT.md is supported by
      the AFL-039 version of the report (`ad79235`); shortening drops detail, not meaning.
- [x] Nothing is lost: every passage removed from REPORT.md appears, as written and with
      its record citations, in DETAILS.md under a heading REPORT.md points to.
- [x] Every cross-reference resolves in both files, and the README's links into
      `docs/report/` still work.
- [x] Plain style: the main report cites DETAILS.md sections instead of ticket and ADR ids
      where possible.
- [x] AI review: (1) an Opus reviewer compares the new REPORT.md with the `ad79235`
      version (no new or changed claims, identical numbers) and checks DETAILS.md holds
      every removed passage; (2) a rubric check confirms REPORT.md covers what the project
      does with its input and output (§1.1), lines of code and language (§4.5), the
      challenges and how they were handled (§4.3), the number of alternative designs
      explored (§4.4), and a pointer to the README demo.
- [x] No changes to `src/`, `harness/`, `targets/`, `experiments/` or any tag.

## Technical notes (architect)
Report text is written by the orchestrator (lead decision, 2026-11-17); reviewers are
read-only. Word counts use `wc -w` on the file with the References section cut off.

## Test approach (tester)
Word count; a diff of DETAILS.md against `git show ad79235:docs/report/REPORT.md`; a
cross-reference check in both files (every `§n`, `DETAILS.md §n` and figure path resolves);
the two AI reviews above.

## Log
- 2026-11-21 — created (orchestrator, from the lead decision of 2026-11-21: condense the report).
- 2026-11-21 — moved to in-progress (orchestrator). DETAILS.md written as the full text of the report at `ad79235`, unchanged except for its title and a note (a 9-line header; the body diff against `git show ad79235:docs/report/REPORT.md` minus its title line is empty). It therefore holds every removed passage as written, and also repeats the kept text; its sections keep the old numbers, and Appendix A is its own "## Appendix A".
- 2026-11-21 — REPORT.md condensed (orchestrator): 3,500 words by `sed '/^## References$/,$d' docs/report/REPORT.md | wc -w` (4,112 at the first draft). Sections 1–8 and §4.1 kept; References last, unchanged from `ad79235`. Every `DETAILS.md §n` pointer (1.1, 2.1, 3, 4.1–4.5, 5, 5.3, 6.2–6.4, 7, Appendix A) resolves to a DETAILS.md heading; `figures/tlv_parser_coverage.png`, `summary.csv` and `PROVENANCE.md` exist; README links into `docs/report/` unchanged. Moved to review.
- 2026-11-21 — rubric check (reviewer, Sonnet, read-only): PASS on every item (word count, structure, §1.1 input and output, §4.5 lines and languages, §4.3 challenges and handling, §4.4 count 19 with 19 rows, table and bullet counts, README demo pointer and links). Flags: total exactly at the cap; §4 at 1,102 words against ~900, driven by the required 19-row and 14-row tables and both code-size tables.
- 2026-11-21 — claim review (reviewer, Opus, read-only): BOUNCE (bounce 1). Numbers, references and DETAILS.md completeness passed. Four blocking meaning changes: the push caveat was dropped from the §4.1 commit bullet; the §4.5 authorship sentence lost its "except two groups" clause; the §7 concurrency line had a new "equally in both arms" and lost "official run 1"; the §7 calibration line lost "(arithmetic, not measured)". Nits N1–N6 applied, plus N8 (the "(lead decision, date)" clause dropped). N7 (three disclosures now only in DETAILS.md §4.2: the pre-freeze slip `1679c36`, the missed toy-1 calibration prediction, "only the commit order can be checked") is left for the lead. The reviewer wrote a scratch copy of the old report to a /tmp path outside the repo, against its read-only brief; it is left in place and reported. Fixed by the orchestrator; now 3,493 words. Sent back for re-review.
- 2026-11-21 — claim re-review (reviewer, Opus, read-only, no files written): APPROVE. All four blocking findings fixed; numbers, references, DETAILS.md completeness and cross-references re-checked on the whole body; the trims change no meaning. One optional nit applied by the orchestrator: the push caveat is attributed to CLAUDE.md §7 as in `ad79235`. Final count: see the next entry. Moved to testing.
- 2026-11-21 — final checks (orchestrator): REPORT.md is 3,496 words by `sed '/^## References$/,$d' docs/report/REPORT.md | wc -w` (cap 3,500); DETAILS.md body identical to `ad79235` minus its title line; the reference list is identical to the `ad79235` list (only the heading changed, from a bold "References." line to "## References"). Status set to done for the gated close; the crew-lead re-runs the test approach and makes the gated move.
- 2026-11-21 — closed (crew-lead, Sonnet): the seven DoD checks passed (word count 3,496; DETAILS.md body identical to `ad79235`; pointers resolve; figure and data files exist; no change under src/, harness/, targets/ or experiments/ against `ad79235`; no new tag; docs/papers and results track only .gitkeep), then the gated mv into tickets/done/ ran and was not blocked. The hook printed nothing, so the orchestrator re-ran the gates: `ruff check .` all checks passed; `mypy src` no issues in 8 source files; `pytest` 607 passed, 10 deselected, rc 0.
- 2026-11-21 superseded before commit: the report left the repo (AFL-041, lead decision, 2026-11-21); the condensed REPORT.md was kept as a copy outside the repo and DETAILS.md was not committed.
