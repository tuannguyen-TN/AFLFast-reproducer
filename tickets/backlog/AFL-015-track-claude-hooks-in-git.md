---
id: AFL-015
title: Track Claude hooks and settings in git (restore DoD enforcement on fresh clone)
requirement: NFR reproducibility (PRD §7); CLAUDE.md §5 (reproducibility) and §7 (deterministic enforcement)
paper_ref: n/a (Klees §reproducibility spirit: results must be reproducible by a third party)
module: .gitignore, .claude/settings.json, .claude/hooks/*.py, pyproject.toml, .prettierignore, docs/.DS_Store (untrack only; merged from AFL-021)
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
- [ ] `ruff check .` exits 0 after `.claude/hooks/*.py` are tracked. Decided (human,
      2026-11-07): the hooks are **excluded** from ruff via an explicit `pyproject.toml` entry
      (e.g. `extend-exclude = [".claude/hooks"]` under `[tool.ruff]`), with a comment next to
      it stating why (process tooling, not project code); the ~8 lint errors are not fixed.
      Test: in a fresh clone, `ruff check .` exits 0 and the exclude entry and its comment are
      present in `pyproject.toml`.
- [ ] In a fresh `git clone` of the repo, `git commit -m "no ticket id"` is blocked by
      `require_ticket_in_commit.py`, and `git commit -m "AFL-015 msg"` is not blocked by it.
- [ ] In a fresh clone, moving a ticket into `tickets/done/` while `ruff`, `mypy` or `pytest`
      fails is blocked by `gate_ticket_done.py`.
- [ ] `gate_ticket_done.py` still prefers the project `.venv` (change approved by human
      2026-11-07) and no tracked file contains an absolute path to a local machine.
- [ ] `git ls-files .prettierignore` prints `.prettierignore` (tracked at the repo root), and
      the file contains the uncommented line `**/*.md`, so editor format-on-save (Prettier)
      cannot rewrite tickets, the PRD or ADRs.

Merged from AFL-021 (human decision, 2026-11-07):

- [ ] `.gitignore` contains an uncommented `.DS_Store` line (no leading `/`, so it
      matches in any directory).
- [ ] The human performs `git rm --cached docs/.DS_Store` (agents do not run git
      write operations). The local file is not deleted.
- [ ] After that, `git ls-files | grep DS_Store` prints nothing.
- [ ] After Finder touches a `.DS_Store` in any directory, `git status --porcelain`
      does not list it.

Added in review (human decision, 2026-11-07):

- [ ] `.gitignore` contains an uncommented `.serena/` line, so the untracked Serena
      tool directory never shows in `git status` (AFL-008/AFL-011's `dirty` check
      ignores untracked files regardless). Fact (checked 2026-11-07): `.gitignore`
      line 22 is already `.serena/`; this AC keeps it when the `.claude/` rule is
      rewritten.
- [ ] **`results/` ignored wholesale (human decision, 2026-11-07; rule form fixed,
      human decision, 2026-11-07).** `.gitignore` ignores everything under
      `results/` with the two lines `results/*` and `!results/.gitkeep` (a bare
      `results/` rule cannot be used: git cannot re-include a file inside an
      ignored directory). Today it ignores only `results/**/*.json|png|csv`, so
      crash `.bin` and `queue/` files show as untracked. Tests:
      `git check-ignore -q results/.gitkeep` exits 1 (not ignored);
      `git check-ignore results/x/y.bin` prints the path (exit 0); and
      `git ls-files results/.gitkeep` still lists `results/.gitkeep`.

Added in review (human decision, 2026-11-07): push policy

- [ ] **No auto-push is configured** (CLAUDE.md §7 "Push policy"), and the result is
      documented in this ticket's Log. Checks:
      - no hook in `.git/hooks/` (other than `*.sample`) runs `git push`;
      - no editor or extension setting pushes or syncs on commit (e.g. VS Code/Cursor
        `git.postCommitCommand` set to `push` or `sync`, or any git-autopush extension
        setting), in the workspace `.vscode/` and in the user settings;
      - no git config alias (local, global or system) that pushes.
      Test: make a throwaway local commit on a scratch clone, or check `git status -sb`
      after the next real commit, and confirm origin is unchanged until a manual push.
      Fact (orchestrator, checked 2026-11-07): only `.sample` hooks, no pushing alias, no
      `postCommitCommand`/autopush setting in the repo or user VS Code/Cursor settings, and
      4 commits local and unpushed. The formal check and Log entry are still required.

All `git rm --cached` steps in this ticket (`.headroom_wrap_*` files and
`docs/.DS_Store`) are performed by the human, not by an agent.

## Technical notes (architect)

- `.claude/agents/*` and `.claude/commands/*` are tracked only because they were committed
  before the ignore rule. The targeted ignores make that intentional.
- Order matters: fix or exclude the hook lint errors before unignoring, otherwise the
  done-gate (which runs `ruff check .`) blocks every ticket.
- Fresh-clone verification must run the hooks from the clone, not from this working tree.
- Fix-vs-exclude is decided: exclude (see Log). The rationale goes in a comment next to the
  `pyproject.toml` entry.

## Test approach (tester)

Clone to a temp directory (`git clone <repo> $TMP/clone`), run `ruff check .` there, attempt
a commit without an `AFL-NNN` id and confirm the block message, then attempt a done-move with
a failing check. Confirm `git ls-files` output for the tracked and untracked sets above.
For the `.DS_Store` ACs: `git ls-files | grep DS_Store` (expect no output), `git check-ignore
-v docs/.DS_Store` (expect the `.gitignore` rule), then create a `.DS_Store` in another
directory (e.g. `tests/`) and confirm `git status --porcelain` stays silent about it.
For the `results/` AC: `git check-ignore -q results/.gitkeep; echo $?` (expect 1) and
`git check-ignore results/x/y.bin` (expect the path printed).

## Log

- 2026-11-07 — created (req-engineer) from AFL-001 tester finding
- 2026-11-07 — added .prettierignore AC after Prettier format-on-save reformatted AFL-011 (human decision) (req-engineer)
- 2026-11-07 — batch grooming: decision — exclude `.claude/hooks` from ruff via a commented `pyproject.toml` entry, not fix (hooks are process tooling); ruff AC adjusted to that branch. AFL-021 merged in (its `.DS_Store` ACs appended; module += docs/.DS_Store). The human performs all `git rm --cached` steps (human decision) (req-engineer)
- 2026-11-07 — review fix: added AC that `.gitignore` contains `.serena/` (already present at line 22) (human decision) (req-engineer)
- 2026-11-07 — review fix: added AC that `.gitignore` ignores `results/` wholesale with `results/.gitkeep` still tracked, tested via `git check-ignore results/x/y.bin` and `git ls-files results/.gitkeep` (human decision) (req-engineer)
- 2026-11-07 — review fix: `results/` rule specified as `results/*` + `!results/.gitkeep` (a bare `results/` cannot re-include a file); test adds `git check-ignore -q results/.gitkeep` exits 1 (human decision) (req-engineer)
- 2026-11-07 — review fix: no-auto-push AC (human decision) (req-engineer)
