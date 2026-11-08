# Ticketing System

No work happens without a ticket. A ticket is one markdown file that physically
**moves between the column directories** as it progresses through the SDLC.

## Columns (directories) = SDLC stages
```
backlog/      req-engineer writes here; architect annotates to "ready"
in-progress/  developer implementing
review/       reviewer gate
testing/      tester + experimental-validity gate
done/         crew lead signed off (DoD met)
```
Move a ticket by moving its file: `git mv tickets/backlog/AFL-005-*.md tickets/in-progress/`.

## ID scheme
`AFL-NNN` — zero-padded, assigned in creation order, never reused. Reference the
ID in every commit (`AFL-005: implement havoc stage`) and branch (`afl-005-havoc`).
Commits and pushes are the human's; agents never commit or push. See "Push policy"
in `CLAUDE.md` §7.

## Lifecycle & who moves it
| From → To | Who | Gate |
|---|---|---|
| backlog → in-progress | developer | Definition of Ready (DoR) met |
| in-progress → review | developer | acceptance criteria met + tests + gates green |
| review → testing | reviewer | code review passed (criterion-by-criterion) |
| review → in-progress | reviewer | changes requested (reason in Log) |
| testing → done | tester → crew lead | DoD + validity checklist green |
| testing → in-progress | tester | defect found (reason in Log) |

DoR is defined in `.claude/agents/req-engineer.md` + `.claude/agents/crew-lead.md`; DoD in `.claude/agents/crew-lead.md`.

## Rules
- One ticket = one focused unit of work, traceable to ≥1 FR/NFR in `docs/PRD.md`.
- Every status change is appended to the ticket's **Log** with date + who + why.
- Backward moves are normal; they must carry a reason.
- Use `templates/ticket-template.md` for new tickets.

## Current backlog
See `backlog/INDEX.md` for the full AFL-001..AFL-014 list and FR mapping.
