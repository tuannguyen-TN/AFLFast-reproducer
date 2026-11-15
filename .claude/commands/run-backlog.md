Act as the **orchestrator** of the crew in `.claude/agents/`, following
`CLAUDE.md §7`. Drive the backlog ticket by ticket with supervised autonomy.

Loop until the backlog has no ready ticket:
1. **crew-lead**: pick the lowest-numbered ticket in `tickets/backlog/` whose
   `depends_on` are all in `tickets/done/` and that meets Definition of Ready.
   If none qualifies, stop and report why (likely missing ticket files or an
   unmet dependency).
2. Delegate to the **developer** subagent: move the ticket to
   `tickets/in-progress/`, implement to every acceptance criterion with tests,
   preserve the invariants (blind mutation; arms differ only in `schedule.py`;
   seed-derived randomness), run `ruff check . && mypy src && pytest`, then move
   it to `tickets/review/` and append to its Log.
3. Delegate to the **reviewer** subagent: approve → `tickets/testing/`, or bounce
   → `tickets/in-progress/` with criterion-referenced reasons.
4. Delegate to the **tester** subagent: verify on a clean checkout plus the
   experiment-validity checklist for experiment tickets; pass → ready to close,
   fail → bounce with reasons.
5. **crew-lead**: move the ticket into `tickets/done/`. The done-gate hook runs
   the quality checks automatically; if it blocks, fix and retry.
6. Stage a commit referencing the ticket id, then **STOP and ask me to approve
   it**. Do not auto-commit. (The commit hook will reject a message without an
   AFL-NNN id.)

STOP conditions — pause and ask me, do not continue the loop:
- The chosen ticket is **AFL-001**: run it, show me the two differing edge sets,
  and wait for my explicit GO/NO-GO before any further tickets.
- A ticket **bounces twice** between stages: stop and summarize the blocker.
- Any **git commit**: always wait for my approval first.

After each ticket, print a one-line status and the updated board, then continue.
