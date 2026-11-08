---
id: AFL-020
title: Refresh INDEX.md status and "Suggested next pull" paragraph
requirement: NFR (process); crew-lead board hygiene (tickets/README.md)
paper_ref: n/a
module: tickets/backlog/INDEX.md
depends_on: []
status: done
owner: crew-lead
---

## Goal
The Status / "Suggested next pull" paragraph at the bottom of
`tickets/backlog/INDEX.md` is stale. It lists AFL-005 and AFL-017 as unblocked or
next, but both are done (commits e1ace06 and 8752446). Bring it in line with the
board.

## Acceptance criteria
- [ ] The Status line lists as done exactly the tickets whose files are in
      `tickets/done/` at the time of the edit (including AFL-005 and AFL-017).
- [ ] No ticket in `tickets/done/` is named as unblocked or as a suggested next pull.
- [ ] Every ticket named as "unblocked" has all its `depends_on` ids in
      `tickets/done/`.
- [ ] AFL-018 is still described as not ready until its open question is decided
      (unless the human has decided it by then, in which case the Log says so).
- [ ] The "Suggested next pull" names ≥1 unblocked ticket and gives a one-line
      reason. The choice is confirmed by the human before the edit is committed.
- [ ] AFL-020's own edit changes only the Status / 'Suggested next pull' paragraph.
      Any table-row changes in the same commit come from other tickets in this batch
      (AFL-007, AFL-008, AFL-013, AFL-018 rows; new rows AFL-019–AFL-022) and are
      verified by those tickets, not here. AFL-020 adds, removes or retitles no table
      row itself.
      Evidence (orchestrator, 2026-11-07, from `git diff -U0 -- tickets/backlog/INDEX.md`).
      Row changes and the ticket each came from:
      - AFL-007, AFL-009 added to depends_on: AFL-007's ADR-0005 replay decision.
      - AFL-008, modules += pyproject.toml, README: AFL-008's `pip install -e .` criterion.
      - AFL-013, AFL-007 added to depends_on: AFL-013's shared-extractor/crash_events decision.
      - AFL-018, retitled, modules widened: AFL-018's signal-rule decision.
      - AFL-019 to AFL-022, new rows: their own ticket creation.
      None of these is AFL-020's.

## Technical notes (architect)
Docs-only. No code. Check `tickets/done/` and each ticket's `depends_on` at edit
time, since the board may have moved since this ticket was filed.

## Test approach (tester)
Compare the paragraph against `ls tickets/done/` and the `depends_on` front matter
of each named ticket. Inspect `git diff` for table-row changes.

## Log
- 2026-11-07 — created (req-engineer) from AFL-005 close follow-ups (human decision)
- 2026-11-07 — review fix: INDEX AFL-018 row retitled/re-moduled to the decided rule; Status / "Suggested next pull" paragraph refreshed (done = AFL-001..005, AFL-017; unblocked list checked against depends_on; AFL-018 decided and DoR; AFL-019/021 superseded; next pull AFL-006) (human decision) (req-engineer)
- 2026-11-07 — paragraph refreshed in the batch-grooming commit (crew-lead)
- 2026-11-07 — review fix: "no table row changes" AC reworded to allow the AFL-018 row change; the AC predated fix 1, which required that row change. Status stays done (human decision) (req-engineer)
- 2026-11-07 — review fix: row AC widened to also allow the AFL-013 row change, because AFL-013's depends_on is `[AFL-003, AFL-007]` and its INDEX Depends-on cell had to be corrected to match (AFL-013 also removed from "Unblocked now", since AFL-007 is not done) (human decision) (req-engineer)
- 2026-11-07 — review fix: Status paragraph notes the AFL-018/AFL-022 same-file sequencing (human decision) (req-engineer)
- 2026-11-07 — review fix: row criterion reworded from an enumerated row list to 'paragraph-only own-edit', because the enumeration kept going stale as the batch grew (human decision) (req-engineer)
