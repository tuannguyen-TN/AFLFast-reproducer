---
id: AFL-021
title: Untrack docs/.DS_Store and ignore .DS_Store everywhere
requirement: NFR (process / reproducibility hygiene, PRD §7)
paper_ref: n/a
module: .gitignore
depends_on: []
status: superseded
owner: developer
---

## Goal
`docs/.DS_Store` is tracked, and Finder keeps modifying it, so `git status` is
never clean. Ignore `.DS_Store` in every directory and remove the tracked copy from
the index.

## Acceptance criteria
- [ ] `.gitignore` contains an uncommented `.DS_Store` line (no leading `/`, so it
      matches in any directory).
- [ ] The human performs `git rm --cached docs/.DS_Store` (agents do not run git
      write operations). The local file is not deleted.
- [ ] After that, `git ls-files | grep DS_Store` prints nothing.
- [ ] After Finder touches a `.DS_Store` in any directory, `git status --porcelain`
      does not list it.

## Technical notes (architect)
AFL-015 also edits `.gitignore` (replacing the blanket `.claude/` rule). The two may
be done in the same change, but they are independent: neither depends on the other,
and each can be verified on its own. If done together, the commit message carries
both ids.

## Test approach (tester)
Run `git ls-files | grep DS_Store` (expect no output) and `git check-ignore -v
docs/.DS_Store` (expect the `.gitignore` rule). Create a `.DS_Store` in another
directory (e.g. `tests/`) and confirm `git status --porcelain` stays silent about it.

## Log
- 2026-11-07 — created (req-engineer) from AFL-005 close follow-ups (human decision)
- 2026-11-07 — batch grooming: merged into AFL-015 (ACs appended there; module += docs/.DS_Store); status superseded, work tracked under AFL-015 (human decision) (req-engineer)
