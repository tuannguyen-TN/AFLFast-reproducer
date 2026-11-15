Act as the **req-engineer** subagent. In one pass, create every ticket file
listed in `tickets/backlog/INDEX.md` that does not yet exist in `tickets/backlog/`.

Currently missing (do NOT touch the existing AFL-001, AFL-006, AFL-011):
AFL-002, AFL-003, AFL-004, AFL-005, AFL-007, AFL-008, AFL-009, AFL-010,
AFL-012, AFL-013, AFL-014.

For each missing ticket:

1. Start from `tickets/templates/ticket-template.md`.
2. Fill the frontmatter from the INDEX row: `id`, a clear `title`, the
   `requirement` (the FR/SC column), the `module`, and `depends_on` exactly as the
   INDEX lists them. Set `status: backlog` and `owner: developer` (or the right
   role).
3. Add the matching `paper_ref` where relevant (AFLFast for the schedule/energy
   work, Klees for the campaign/stats/dedup work; `n/a` for plumbing).
4. Write objective, testable **acceptance criteria** traceable to that FR in
   `docs/PRD.md §6` — mirror the PRD's acceptance wording, don't invent scope.
5. Preserve the project invariants where they apply (blind mutation; arms differ
   only in `schedule.py`; seed-derived randomness).
6. Name the file `tickets/backlog/AFL-0NN-<slug>.md` matching the INDEX title.
7. Seed the Log with a single "created (req-engineer)" line.

Then switch to the **architect** subagent and add a short **Technical notes**
section to each new ticket (interfaces, relevant ADR, approach constraints) so it
meets the Definition of Ready.

Do NOT implement anything, write any source code, or move any ticket out of
`tickets/backlog/`. When done, run `/board` and report which tickets are now
ready to start (dependencies satisfied) versus still blocked.
