Drive the next unit of work through the SDLC defined in `.claude/agents/crew-lead.md`.

1. As **crew-lead**, pick the highest-priority ticket in `tickets/backlog/` whose
   `depends_on` are all done (default to the lowest AFL-NNN; honour INDEX.md).
   Confirm it meets Definition of Ready.
2. As **developer**, move it to `tickets/in-progress/`, implement it to every
   acceptance criterion with tests, preserve the invariants, run
   `ruff check . && mypy src && pytest`, then move it to `tickets/review/` and
   update its Log. Commit referencing the ticket id.
3. As **reviewer**, review it criterion by criterion; approve to `tickets/testing/`
   or bounce to `tickets/in-progress/` with reasons.
4. As **tester**, verify on a clean checkout (+ experiment-validity checklist for
   experiment tickets); pass to `tickets/done/` via crew-lead DoD sign-off, or
   bounce with reasons.
Report what moved and where it ended up. Stop and ask me before starting if the
chosen ticket is AFL-001 (the go/no-go spike) and it has not yet been run.
