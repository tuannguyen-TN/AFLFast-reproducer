---
id: AFL-015
title: Track Claude hooks and settings in git (restore DoD enforcement on fresh clone)
requirement: NFR reproducibility (PRD §7); CLAUDE.md §5 (reproducibility) and §7 (deterministic enforcement)
paper_ref: n/a (Klees §reproducibility spirit: results must be reproducible by a third party)
module: .gitignore, .claude/settings.json, .claude/hooks/*.py, pyproject.toml
depends_on: [AFL-001]
status: backlog
owner: developer
---

## Goal

`.gitignore` line 8 is `.claude/`, so `.claude/settings.json` and `.claude/hooks/*.py`
(`require_ticket_in_commit.py`, `gate_ticket_done.py`), the deterministic Definition-of-Done
gates of CLAUDE.md §7, are untracked. A fresh clone or grader gets no gates. Make the gates
part of the repository, and keep tool scratch files out of it.

## Acceptance criteria

- [ ] `.gitignore` no longer contains the blanket `.claude/` rule. It instead ignores
      exactly `.claude/.headroom_wrap_*` and `.claude/settings.local.json`.
- [ ] `git ls-files .claude/settings.json .claude/hooks` lists `settings.json` and both
      hook scripts (`require_ticket_in_commit.py`, `gate_ticket_done.py`).
- [ ] `git ls-files .claude | grep headroom_wrap` prints nothing (the tracked
      `.headroom_wrap_marker.json`, `.headroom_wrap_owners.json` and
      `.headroom_wrap_settings.lock` are removed from the index via `git rm --cached`; the
      human performs the git operations).
- [ ] `ruff check .` exits 0 with `.claude/hooks/*.py` in scope: the ~8 current ruff errors
      are either fixed or the hooks are excluded via an explicit `pyproject.toml` entry. The
      choice and its rationale are recorded in this ticket's Log.
- [ ] In a fresh `git clone` of the repo, `git commit -m "no ticket id"` is blocked by
      `require_ticket_in_commit.py`, and `git commit -m "AFL-015 msg"` is not blocked by it.
- [ ] In a fresh clone, moving a ticket into `tickets/done/` while `ruff`, `mypy` or `pytest`
      fails is blocked by `gate_ticket_done.py`.
- [ ] `gate_ticket_done.py` still prefers the project `.venv` (change approved by human
      2026-11-07) and no tracked file contains an absolute path to a local machine.

## Technical notes (architect)

- `.claude/agents/*` and `.claude/commands/*` are tracked only because they were committed
  before the ignore rule. The targeted ignores make that intentional.
- Order matters: fix or exclude the hook lint errors before unignoring, otherwise the
  done-gate (which runs `ruff check .`) blocks every ticket.
- Fresh-clone verification must run the hooks from the clone, not from this working tree.
- Record the fix-vs-exclude decision for the hooks in the Log and, if excluded, in a comment
  next to the `pyproject.toml` entry.

## Test approach (tester)

Clone to a temp directory (`git clone <repo> $TMP/clone`), run `ruff check .` there, attempt
a commit without an `AFL-NNN` id and confirm the block message, then attempt a done-move with
a failing check. Confirm `git ls-files` output for the tracked and untracked sets above.

## Log

- 2026-11-07 — created (req-engineer) from AFL-001 tester finding
