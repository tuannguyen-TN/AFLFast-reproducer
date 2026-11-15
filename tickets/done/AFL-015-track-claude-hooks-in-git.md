---
id: AFL-015
title: Track Claude hooks and settings in git (restore DoD enforcement on fresh clone)
requirement: NFR reproducibility (PRD §7); CLAUDE.md §5 (reproducibility) and §7 (deterministic enforcement)
paper_ref: n/a (Klees §reproducibility spirit: results must be reproducible by a third party)
module: .gitignore, .claude/settings.json, .claude/hooks/*.py, .claude/hooks/git_policy.py, .claude/commands/, tests/test_git_policy_hook.py, pyproject.toml, .prettierignore, docs/.DS_Store and root .DS_Store (untrack only; merged from AFL-021)
depends_on: [AFL-001]
status: done
owner: developer
---

## Goal

`.gitignore` line 8 is `.claude/`, so `.claude/settings.json` and `.claude/hooks/*.py`
(`require_ticket_in_commit.py`, `gate_ticket_done.py`), the deterministic Definition-of-Done
gates of CLAUDE.md §7, are untracked. A fresh clone or grader gets no gates. Make the gates
part of the repository, and keep tool scratch files out of it.

## Acceptance criteria

- [x] `.gitignore` no longer contains the blanket `.claude/` rule. It instead ignores
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

- [x] `.gitignore` contains an uncommented `.DS_Store` line (no leading `/`, so it
      matches in any directory).
- [ ] The human performs `git rm --cached docs/.DS_Store` (agents do not run git
      write operations). The local file is not deleted.
- [ ] **Root `.DS_Store` too (human decision, 2026-11-12).** The root `.DS_Store`
      is also tracked (`git ls-files | grep DS_Store` lists `.DS_Store` and
      `docs/.DS_Store`). The human also performs `git rm --cached .DS_Store` (repo
      root). The local file is not deleted.
- [ ] After both, `git ls-files | grep DS_Store` prints nothing.
- [ ] After Finder touches a `.DS_Store` in any directory, `git status --porcelain`
      does not list it.

Added in review (human decision, 2026-11-07):

- [x] `.gitignore` contains an uncommented `.serena/` line, so the untracked Serena
      tool directory never shows in `git status` (AFL-008/AFL-011's `dirty` check
      ignores untracked files regardless). Fact (checked 2026-11-07): `.gitignore`
      line 22 is already `.serena/`; this AC keeps it when the `.claude/` rule is
      rewritten.
- [x] **`results/` ignored wholesale (human decision, 2026-11-07; rule form fixed,
      human decision, 2026-11-07).** `.gitignore` ignores everything under
      `results/` with the two lines `results/*` and `!results/.gitkeep` (a bare
      `results/` rule cannot be used: git cannot re-include a file inside an
      ignored directory). Today it ignores only `results/**/*.json|png|csv`, so
      crash `.bin` and `queue/` files show as untracked. Tests:
      `git check-ignore -q results/.gitkeep` exits 1 (not ignored);
      `git check-ignore results/x/y.bin` prints the path (exit 0); and
      `git ls-files results/.gitkeep` still lists `results/.gitkeep`.

Added in review (human decision, 2026-11-07): push policy

- [x] **No auto-push is configured** (CLAUDE.md §7 "Push policy"), and the result is
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

Added scope (human decision, 2026-11-12):

- [ ] **The two slash-command files are tracked.** `git ls-files .claude/commands`
      lists `groom-backlog.md` and `run-backlog.md`. Reason: CLAUDE.md §7 names
      `/run-backlog` as a driver, so a fresh clone must have it. The human stages them
      (see "Human commit list (consolidated)" below).
- [ ] **`.claude/` inventory.** After the commit, `git status --porcelain
      --untracked-files=all .claude/` prints nothing. Every file under `.claude/`
      is then either tracked or deliberately ignored, and the ignored set is
      exactly `.claude/settings.local.json` and `.claude/.headroom_wrap_*`. Test:
      `git status --porcelain --ignored --untracked-files=all .claude/` prints
      only `!!` lines, and each names `.claude/settings.local.json` or a
      `.claude/.headroom_wrap_*` file.
      - Fact (orchestrator, checked 2026-11-12): the untracked files under
        `.claude/` today are `.claude/commands/groom-backlog.md`,
        `.claude/commands/run-backlog.md`, `.claude/hooks/gate_ticket_done.py`,
        `.claude/hooks/require_ticket_in_commit.py` and `.claude/settings.json`.
      - `.claude/agents/tester.md` is modified, but it belongs to the separate
        grooming commit, not to AFL-015. This AC is therefore checked after both
        commits (AFL-015's and the grooming commit).
- [ ] **Git write commands need the human, enforced deterministically.**
      `.claude/settings.json` enforces the commit and push policy (CLAUDE.md §7,
      "Push policy" and "Commit policy"), so that an agent in auto mode cannot
      commit or push on its own:
      - `git push` is **denied outright**;
      - `git commit`, `git rm`, `git reset`, `git checkout --` and `git restore`
        each **require the human's explicit approval**.

      The mechanism (permission rules, a PreToolUse hook, or both) is for the
      architect's notes. A research task on how Claude Code 2.1.322 treats these
      in auto mode is in flight. Tests:
      - (a) An agent attempting `git push` is blocked before the command runs.
        The test uses a harmless form that would not reach origin even if it ran,
        e.g. `git push --dry-run` against a nonexistent remote. The block must
        come from the policy, not from the remote.
      - (b) An agent attempting `git commit` gets a human approval prompt and is
        not auto-approved.
      - (c) The policy also catches compound commands, e.g. `cd <repo> && git
        push`. If the mechanism cannot catch some form, this ticket names that
        form explicitly as a known limit.
      - (d) The behaviour of the existing `require_ticket_in_commit.py` is
        unchanged.
      - (e) (human decision, 2026-11-12) A broad allow rule in the git-ignored
        `.claude/settings.local.json`, e.g. `Bash(git:*)` or `Bash(git push:*)`,
        cannot re-enable `git push` for an agent: with such a rule present, test
        (a) still blocks. If a local allow rule can override the policy, the
        mechanism must close that gap (for example with a PreToolUse hook). A
        research task on settings precedence is in flight; this test does not
        choose the mechanism.

      Implemented (developer, 2026-11-12): permission rules (deny push; ask
      commit/rm/reset/restore/checkout) plus PreToolUse hook `git_policy.py` (exit 2 on
      any push form; `ask` JSON for the other four); all hooks `onFailure: block`.
      Known limits (test (c)):
      - pushes run indirectly: from scripts, git aliases, `make`, `python -c`, etc.
        (the hook and rules see only the command text);
      - `disableAllHooks` in `settings.local.json` turns the hook layer off; the
        permission rules still hold for the literal forms (`git push *`, `git * push *`);
      - a Claude Code mod or plugin that handles permission checks can approve a call
        that the rules would otherwise ask about, so this policy assumes no such mod is
        installed.
      Status of tests: offline hook tests in `tests/test_git_policy_hook.py` prove the
      hook verdicts (push blocked incl. compound, VAR=x, `command`, `-C`, `-c`,
      `/usr/bin/git`, `sh -c`, `bash -c`, `eval`, `$(...)`; ask for the 5 write
      subcommands; read-only commands pass; malformed stdin passes; (c) and (d) offline:
      `require_ticket_in_commit.py` unchanged). Live tests (a) agent push blocked,
      (b) commit prompts the human, (e) a `settings.local.json` allow cannot re-enable
      push are NOT run: for the tester.

- [ ] **`git config` asks (human decision, 2026-11-12).** `git config` requires the
      human's approval, in both layers: `"Bash(git config *)"` is in
      `permissions.ask` of `.claude/settings.json`, and `config` is in the `ASK`
      alternation of `git_policy.py`. Rationale: an alias is the cheapest indirect push.
      Tests (offline, `tests/test_git_policy_hook.py`): `git config alias.p push` -> ask;
      `git -C x config --get user.name` -> ask.

- [ ] **`-c` / `--config-env` asks (added 2026-11-12, human decision).** Any git invocation
      with a `-c` or `--config-env` global option before the subcommand (`git -c k=v x`,
      `git -ck=v x`, `git --config-env=k=ENV x`, `git --config-env k=ENV x`,
      `git -C dir -c k=v x`, after `&&` or `FOO=1`) forces the human approval prompt
      (new `CFG` regex in `git_policy.py`). Fails closed. Unchanged: `git -C dir log` and
      `git log -c` pass; `git -c k=v <push>` still blocks (block wins over ask).
      Tests: `tests/test_git_policy_hook.py` (ASKED, PASSED, BLOCKED lists).

Rework after tester F1-F4 (human decision, 2026-11-13). This supersedes every "asks" /
"approval prompt" wording in the ACs above: those decisions are now **deny**.

- [ ] **F1 (implementation fix).** Line continuations are normalised before matching;
      `ARG` accepts backslash escapes, `$'..'` and quotes inside a token; `super-prefix` and
      `config-env` join the space-form option list in `PREFIX` and `CFG`. Denied:
      `git -C a\ b -c ...`, `git -C $'a b' -c ...`, `git -C a"b c" -c ...`, `git \<newline> -c ...`,
      `git -C d \<newline> -c ...`, `git --super-prefix x -c ...`; blocked as pushes:
      `git -C a\ b <push>`, `git \<newline> <push>`, `git --super-prefix x <push>`. Still pass:
      `git -C d log`, `git log -c`, `git grep -c x`, `git log --oneline -1`.
- [ ] **F2.** `\bGIT_CONFIG_(COUNT|PARAMETERS|KEY_n|VALUE_n|GLOBAL|SYSTEM)\b` anywhere in the
      command is denied like `-c`.
- [ ] **F3.** `git --config-env k=E <push>` blocks (push message), not the generic deny.
- [ ] **F4: deny instead of ask (human decision, 2026-11-13).** Every former `ask` (commit, rm,
      reset, restore, checkout, config, `-c` / `--config-env`, `GIT_CONFIG_*`) is now exit 2 with
      stderr "Blocked by git policy hook: the human runs this git command in their own terminal
      (CLAUDE.md section 7). For a commit, the orchestrator writes the message to a file and the
      human runs `git commit -F <file>`." Reason: in auto mode an "ask" was settled without a
      human, so ask enforces nothing; deny holds in every mode. The push block is unchanged.
      (Superseded 2026-11-13 by AC "(d) settings.json denies" below: the `permissions.ask` rules
      are now `deny` rules.)
- [ ] **F5 (human decision, 2026-11-13).** Escaped quotes inside quoted tokens and quoted option
      values containing a space are parsed. `ARG` is the reviewer's tested form, and both bare-flag
      branches (`PREFIX`, `CFG`) end in `{ARG}`. Denied: `git -C $'a\'b' -c k=v log`,
      `git -C "a\"b" -c k=v log`, `git --exec-path="a b" -c k=v log`, `git -C "a\"b" commit -m x`;
      push-blocked: `-C $'a\'b'`, `-C "a\"b"`, `--git-dir="a b"` before the push subcommand.
- [ ] **(d) settings.json denies (human decision, 2026-11-13).** The six `permissions.ask` rules
      are `deny` rules: for each of commit, rm, reset, restore, checkout and config the deny list
      has `Bash(git <verb> *)`, `Bash(git * <verb>)` and `Bash(git * <verb> *)`. The `ask` array is
      removed; the push deny rules and the hooks block are unchanged. Rationale: settings.json is
      the only layer left when hooks are disabled, an "ask" may not reach a human in auto mode, and
      agents no longer commit. **Dropped (lead decision, 2026-11-14):** the restart-based human
      live check below is not performed; see Known gaps. Original text kept for the record:
      Human live check (cannot be run from inside the agent session): in a
      normal-mode session with `"disableAllHooks": true` in `.claude/settings.local.json`, ask the
      agent to run `git -C x commit --dry-run -m "AFL-015 live check"` (a commit-form command with a
      global option); expect "Permission to use Bash with command ... has been denied" from
      settings, not a prompt, and no run. In the same session (human decision, 2026-11-13), ask
      the agent to run `git -C $(git rev-parse --show-toplevel) push --dry-run /nonexistent HEAD`
      (the F6 push form, which with hooks off only settings.json can catch); expect the same
      settings deny, no approval prompt, and the command not run. The `--dry-run` to `/nonexistent`
      means nothing can leave the machine even if the block fails. Then remove the `disableAllHooks` line from
      `.claude/settings.local.json`, restart the session, and confirm with `cat
      .claude/settings.local.json`.
- [ ] **Tracked commit-msg hook, replaces the agent-side ticket-id check for the human flow.**
      `.githooks/commit-msg` (POSIX sh, executable, no venv) rejects a message without an
      `AFL-NNN` id (exit 1, clear message) and accepts one with an id; `#` comment lines are
      ignored (mirrors the intent that only real message text counts). `require_ticket_in_commit.py`
      stays in place; `.claude/settings.json` is unchanged (superseded by AC "(d) settings.json denies" below;
      reviewer note, 2026-11-13). Tests: `tests/test_commit_msg_hook.py`
      (temp repo via subprocess, `core.hooksPath` there only): `-F` without id rejected, with
      `AFL-123` accepted, commented id not counted.
- [ ] **(a) `core.hooksPath` is local git config and does not travel with a clone.** Every
      clone needs `git config core.hooksPath .githooks`; the human runs it (agents are denied
      `git config`). It is a step in README.md's setup and in the fresh-clone live check below.
- [x] **(b) `core.hooksPath` replaces `.git/hooks` completely.** Checked 2026-11-13: `ls .git/hooks`
      holds only `*.sample` files (13 files, 0 non-sample), so nothing is lost.
- [ ] **Dropped (lead decision, 2026-11-14): the throwaway commit and `git reset --soft` would
      rewrite history, which the lead forbids; not performed, see Known gaps. Original text kept:**
      **(c) Commit workflow (human-run live check).** The orchestrator writes the commit message
      to a file; the human runs `git commit -F <file>` in their own terminal; the tracked
      commit-msg hook checks the id. Human-run, plain terminal, after step (a), from the repo
      root (throwaway commit, undone afterwards):
      1. `printf 'no id\n' > /tmp/m1.txt && git commit --allow-empty -F /tmp/m1.txt` -> rejected
         with "Rejected by commit-msg hook ...", exit 1, `git log --oneline -1` unchanged.
      2. `printf 'AFL-015: throwaway\n' > /tmp/m2.txt && git commit --allow-empty -F /tmp/m2.txt`
         -> accepted.
      3. `git reset --soft HEAD~1` -> undoes the throwaway commit; `git log --oneline -1` is
         back to the previous commit.
- [ ] **(d) AFL-015's own commit uses this `-F` flow** (message in a file, human runs
      `git commit -F <file>`).
- [ ] **Updated live checks for F4 (human, normal-mode session).** Ask the agent to run
      `git commit --dry-run --allow-empty -m "AFL-015 live check b"` and
      `git -c core.pager=cat log --oneline -1`: both must be denied with the "human runs this git
      command" message, with no approval prompt. Kept safeguards: the harmless
      `git push --dry-run /nonexistent HEAD` probe (blocked), and `cat .claude/settings.local.json`
      to confirm any allow line added for check (e) is gone. Fresh-clone check: after
      `git config core.hooksPath .githooks` in the clone (human), step (c) behaves as above.
      Evidence (orchestrator, 2026-11-14, live auto-mode session in this repo, hooks on):
      - [x] Commit part: `git commit --dry-run --allow-empty -m "AFL-015 live check b"` was
            DENIED by the hook with "Blocked by git policy hook: the human runs this git command
            in their own terminal (CLAUDE.md section 7)...", no approval prompt, not run.
      - [x] `-c` part: `git -c core.pager=cat log --oneline -1` was DENIED with the same message,
            no prompt.
      - [ ] Push probe: not performed (the lead forbids running push in any form).
      - [ ] `cat .claude/settings.local.json`: not applicable, check (e) is dropped (lead
            decision, 2026-11-14).
      - [ ] Fresh-clone check: not performed. Covered by step (a) being in README.md and the
            human running `git config core.hooksPath .githooks` right after the AFL-015 commit.

**Threat model (human decision, 2026-11-12).** The policy prevents accidental or careless pushes and unapproved commits by agents. It does not attempt to stop deliberate evasion. Pushes started indirectly (scripts, make, python -c, aliases created before the git config rule) are documented limits.

Known gaps (2026-11-12):

- CLOSED (2026-11-12, human decision): `git -c alias.p=<push> p`, an inline alias with no config write. Now denied (exit 2) via `CFG` (see the `-c` / `--config-env` AC; ask became deny under F4).
- Deliberate evasion, out of the threat model (F8, 2026-11-13): a quoted or escaped command
  word, subcommand or option (`'git'`, `"push"`, `pu''sh`, `\push`, `'commit'`, `'-c'`,
  `"-c"`, `$'\x2dc'`), or a command word produced by substitution (`$(command -v git)` then
  the push). No code change. The settings.json deny rules do not catch these forms either
  (they match the literal command text; not checked live).
- Observed 2026-11-13: while editing this ticket, the crew-lead (no Edit tool) wrote the text with an inline Python script that split the word "git" so the hook's text check would not match a git subcommand in it. Benign (ticket write only, within its write scope; no git command ran), but it is a logged instance of the F8 deliberate-evasion gap: text-matching guards can be evaded by the agent they guard. Mitigations: ticket-text edits go to agents with Edit/Write; settings.json deny rules and the git-level commit-msg hook do not depend on the agent's wording (the commit-msg hook enforces only the AFL-NNN id and is skipped by --no-verify, so it is not a commit block).
- `--attr-source` (newer git) is not in `SPACE_OPT`. Its space form (`--attr-source HEAD`
  then push, commit or `-c`) may pass. Not checked: the local Apple git 2.39.5 rejects the option.
- F6 and F7: CLOSED (2026-11-13, human decision), see the Log.
- Residual F6 forms (reviewer, 2026-11-13; for the human to confirm as deliberate evasion): the hook cannot
  close a substitution nested more than one level deep, one with a quoted or escaped paren inside, or
  one containing a `case` pattern `)`. Such a word cannot be read, so the subcommand after it is not seen.
  Examples: `-C $(echo $(echo $(pwd)))`, `-C $(echo "(")`, `-C $(echo \( )`, `-C $(( (1+2)*3 ))`.
  The space-free deep form `-C $(echo$(echo$(pwd)))` was caught before F6 and now passes.
  The settings.json rules `Bash(git * push)` and `Bash(git * <verb> *)` should still catch the push and
  verb forms (not checked live).
- The `-c` / `--config-env` / `GIT_CONFIG_*` injection forms are enforced only by the hook:
  settings.json has no rule for them, so with hooks disabled they are not blocked (human
  decision, 2026-11-13).
- Indirect pushes through scripts, make or `python -c`.
- Aliases created before the config rule.
- Restart-based live checks ((d) settings deny with hooks disabled, (e) local allow cannot
  re-enable push) and the throwaway-commit check (c): not performed live; covered by offline
  tests (tests/test_git_policy_hook.py, tests/test_commit_msg_hook.py) (lead decision,
  2026-11-14). The commit-msg hook's accept path is exercised by every commit after
  `core.hooksPath` is set.
- CLOSED (2026-11-12): gap 1, `--work-tree` / `--git-dir` (and `--namespace`) in space form
  followed by the push subcommand. `PREFIX` now matches
  `(?:-[Cc]|--(?:git-dir|work-tree|namespace))\s+{ARG}`. Tests: `git --work-tree x push`
  and `git --git-dir /tmp/r push` (path without "git" in it, so the block comes from the
  new option) -> blocked; `git add -p push.md`, `cat CLAUDE.md`, `git log --oneline` still pass.

Over-blocking, kept on purpose: grep, heredocs or `commit -m` text that contain the push
phrase are blocked. Workarounds: use the Edit/Write/Grep tools for text that mentions it,
and `git commit -F <file>` for commit messages that mention it. The reviewer counted 12
repo lines and 0 of 23 commit bodies containing the phrase, so trips are rare and no change
is made.

Known gap, accepted (human decision, 2026-11-13): the broad settings.json deny patterns
`Bash(git * <verb>)` and `Bash(git * <verb> *)` over-match any git command that merely contains the
word, e.g. `git log --grep config` or `git log --grep commit`. This fail-closed cost is accepted;
the Grep tool and `rev-parse` cover the reads. With hooks on, the hook's narrower regex is the
tighter layer, but the rules apply regardless.

Open human decision (not decided): whether to add a git pre-push hook as an extra layer.

Tester's live-check list (before the human commit is exercised; updated 2026-11-13, F4): (a) push blocked, (b)
commit is DENIED by the hook (exit 2, "the human runs this git command" message), with no approval prompt, (c) compound commands at the rule layer (e.g. `cd <repo> && git
push`), (e) a `settings.local.json` allow cannot re-enable push; plus: the deny rule
matches a bare push with no arguments (the first deny rule, push followed by ` *`, versus
the second, `Bash(git * push)`; the hook covers the form regardless).

Human live checks (tester, 2026-11-12; the agent cannot run these without prompting the human
or editing settings). Run each in a live Claude Code session in this repo, auto mode on:

- (b) Commit is denied (F4, human decision 2026-11-13; this replaces the former "prompts the human").
  1. Ask the agent to run `git commit --dry-run --allow-empty -m "AFL-015 live check b"`
     (`--dry-run` creates no commit even if it ran).
  2. Expected: DENY (hook exit 2, stderr "Blocked by git policy hook: the human runs this git
     command in their own terminal ..."). No approval prompt appears; the command does not run.
  3. Confirm `git log --oneline -1` is unchanged.
  - [x] Checked (orchestrator, 2026-11-14, live auto-mode session in this repo, hooks on): the
        command was DENIED by the hook with "Blocked by git policy hook: the human runs this git
        command in their own terminal (CLAUDE.md section 7)...", no approval prompt, not run.
- **Dropped (lead decision, 2026-11-14): restart-based check, not performed; see Known gaps.
  Original text kept:** (e) A `settings.local.json` allow cannot re-enable push.
  1. Add `"Bash(git push *)"` to `permissions.allow` in `.claude/settings.local.json`
     (optionally also `"Bash(git:*)"`).
  2. Restart the session (settings load at start).
  3. Ask the agent to run `git push --dry-run /nonexistent HEAD`. Expected: blocked (hook stderr
     "Blocked by git policy hook: agents never run git push; ..." or a permission deny). No
     prompt, no run.
  4. Rule layer under the allow: ask the agent to run `git log --oneline -1 --grep push` (the
     hook passes it). Expected: "Permission to use Bash with command ... has been denied" (deny
     beats allow).
  5. Remove the allow line(s) from `.claude/settings.local.json` and restart the session.
  6. (added 2026-11-12, human decision) Run `cat .claude/settings.local.json` and confirm the
     allow line is gone. The file is gitignored, so `git status` will not show it if the line
     was left behind.
- Do NOT test the bare-push deny rule with hooks disabled: a bare `git push` targets origin
  (main is ahead of origin), so a rule miss would really push. The bare form stays proven by
  the hook only (see the tester Log entry).

All `git rm --cached` steps in this ticket (`.headroom_wrap_*` files,
`docs/.DS_Store` and the root `.DS_Store`) are performed by the human, not by an
agent.

### Human commit list (consolidated, 2026-11-13)

The ONE list. It supersedes every earlier command list in the Log. Run from the repo root
in your own terminal (agents are denied git writes). Every path was checked to exist on
2026-11-13; no `.DS_Store` is listed.

```
git rm --cached .claude/.headroom_wrap_settings.lock
git rm --cached .DS_Store docs/.DS_Store
git add .gitignore
git add .claude/hooks/gate_ticket_done.py .claude/hooks/git_policy.py .claude/hooks/require_ticket_in_commit.py
git add .claude/settings.json
git add .claude/commands/groom-backlog.md .claude/commands/run-backlog.md
git add .githooks/commit-msg
git add tests/test_commit_msg_hook.py tests/test_git_policy_hook.py
git add README.md CLAUDE.md
git add tickets/backlog/AFL-015-track-claude-hooks-in-git.md   # stages the deletion of the tracked backlog copy
git add tickets/done/AFL-015-track-claude-hooks-in-git.md   # final path; see the note below
git add pyproject.toml           # one hunk only: the [tool.ruff] extend-exclude
git commit -F <message file>
```

- `.claude/hooks/` has exactly three files (all listed). `.claude/commands/` also holds
  tracked `board.md`, `groom.md`, `next-ticket.md`, `review-ticket.md`: unchanged, not listed.
- `README.md` and `CLAUDE.md`: checked with `git diff README.md CLAUDE.md` (2026-11-13). Each
  has exactly one hunk and both are AFL-015's: README.md = the `core.hooksPath` setup step;
  CLAUDE.md = the section 7 "Working with the git-write policy" bullets. No other ticket's
  hunks, so plain `git add` is right.
- `pyproject.toml`: `git diff pyproject.toml` shows exactly one hunk, the AFL-015 `[tool.ruff]`
  `extend-exclude` entry and its comment, so a plain `git add` is right. Nothing is staged
  (`git diff --cached` is empty) and AFL-009 is already committed (2fc1381) (reviewer, 2026-11-13,
  orchestrator fact check).
- `.claude/settings.json` is staged unconditionally: the Q1 decision is made (the `ask` rules
  became `deny` rules, 2026-11-13).
- The ticket's own line says `tickets/done/...` (crew-lead, 2026-11-13, after the close move to done; earlier `tickets/testing/...`). The human uses whichever folder the ticket is
  in at commit time (`ls tickets/*/AFL-015-*`); later moves change the path.
- Not AFL-015 (do not stage here): `.claude/agents/tester.md` (grooming commit), other tickets.

## Technical notes (architect)

- `.claude/agents/*` are tracked only because they were committed before the ignore rule;
  the targeted ignores make that intentional. `.claude/commands/` holds tracked commands
  plus two new files (`groom-backlog.md`, `run-backlog.md`) that are untracked until the
  human runs `git add` (see the Added scope AC and the Log).
- Order matters: fix or exclude the hook lint errors before unignoring, otherwise the
  done-gate (which runs `ruff check .`) blocks every ticket.
- Fresh-clone verification must run the hooks from the clone, not from this working tree.
- Fix-vs-exclude is decided: exclude (see Log). The rationale goes in a comment next to the
  `pyproject.toml` entry.

## Test approach (tester)

Clone to a temp directory (`git clone <repo> $TMP/clone`), run `ruff check .` there, attempt
a commit without an `AFL-NNN` id and confirm the block message, then attempt a done-move with
a failing check. Confirm `git ls-files` output for the tracked and untracked sets above.
For the `.DS_Store` ACs: `git ls-files | grep DS_Store` (expect no output; before the fix it
lists both `.DS_Store` and `docs/.DS_Store`), `git check-ignore -v docs/.DS_Store` and
`git check-ignore -v .DS_Store` (expect the `.gitignore` rule for each), then create a `.DS_Store` in another
directory (e.g. `tests/`) and confirm `git status --porcelain` stays silent about it.
For the `results/` AC: `git check-ignore -q results/.gitkeep; echo $?` (expect 1) and
`git check-ignore results/x/y.bin` (expect the path printed).

## Review (reviewer, 2026-11-12, re-review after bounce 1 plus the added scope)

Verdict: APPROVED to testing. The bounce count stays at 1 of 2.

- Diffs: `.gitignore` and the `[tool.ruff]` `extend-exclude` hunk are unchanged since the last approval. `git diff .prettierignore` is empty. The `pyproject.toml` pytest hunk is AFL-009's (staged), and the index was not touched.
- `settings.json` schema: `permissions` (deny push, ask commit/rm/reset/restore/checkout) is at the top level. `onFailure: "block"` is on each of the three hook entries. No absolute paths; only `$CLAUDE_PROJECT_DIR`. `checkout` is asked in every form, which is a superset of the AC's `checkout --` and acceptable.
- Existing hooks: `require_ticket_in_commit.py` and `gate_ticket_done.py` have mtime 2026-11-07, so they are unchanged. Test (d) is offline-proven.
- `git_policy.py`, offline probes: every plausible form in the threat model is blocked: two spaces, tab, newline, `env`, `command`, backticks, `$(...)`, `sh -c` and `/usr/bin/git`. Commit with `-c user.name=x` asks, and `commit -F file` asks.
- Known gaps (not a bounce under the human's threat model; the human decides):
  - (1) `--work-tree x` and `--git-dir /x` in space-separated form, followed by the push subcommand, pass the hook. `--git-dir .git` is blocked only by accident, because `.git` contains `git`. One-line fix: change `-[Cc]\s+{ARG}` to `(?:-[Cc]|--(?:git-dir|work-tree|namespace))\s+{ARG}`.
  - (2) `-c alias.p=<push> p` passes. This goes with the pending `git config` follow-up.
  - (3) A quoted `"git"` passes; this is out of scope (deliberate).
- Over-blocking fails closed, as intended. The hook blocks any Bash text with the literal git-then-push sequence: heredoc ticket text, grep for it, and commit messages that mention it. Frequency: 12 lines in the whole repo (10 in this ticket, 2 in CLAUDE.md) and 0 of 23 commit bodies. So it trips only during push-policy editing, and the Edit/Write, Grep-tool and `commit -F` workarounds cover that. No change recommended. Observed live: the hook blocked this reviewer's own heredoc that wrote this section, because the first draft quoted the deny rule literally.
- The rule with git, a wildcard, then push also denies `git grep <push> ...` and `git log --grep <push> ...`. These are rare and fail closed.
- Fail-safe: malformed stdin exits 0, and all parsing is inside `try`. So `onFailure: block` bites only when the interpreter is missing or times out, and the deny rules still hold the literal forms. That split is coherent under the threat model.
- Inventory: the 6 untracked files under `.claude/` are all on the latest human command list, and so is `tests/test_git_policy_hook.py`. The ignored set today is `.claude/settings.local.json`. After the human runs `git rm --cached`, `.headroom_wrap_settings.lock` joins it (`check-ignore --no-index` matches `.gitignore:8`). `.claude/agents/tester.md` belongs to the grooming commit.
- Gates: ruff exit 0, mypy exit 0 (8 files), pytest 163 passed, 2 deselected. 34 of those tests are the hook tests.
- Non-blocking notes:
  - (a) The third known-limit bullet ("a mod handling `tool.check` ...") is unclear. Reword it or drop it.
  - (b) Test (c) also needs a live check of the rule layer, not only the offline hook check. Add it to the tester's live list with (a), (b) and (e).
  - (c) The tester should confirm in a live session that the first deny rule (push followed by ` *`) matches the bare form with no arguments. The hook covers that form in any case.
- Pending added scope (human, 2026-11-12; not a bounce):
  - `git config` on the ask list in both the rules and the hook;
  - the threat-model text in this ticket;
  - the Edit/Write and `commit -F` workarounds, in this ticket and in CLAUDE.md section 7;
  - a record that the optional git pre-push hook is an open human decision.
  This follow-up must land before the tester's live checks.

## Tester re-test: `-c` / `--config-env` ask rule (2026-11-12)

- Gates: ruff exit 0; mypy exit 0 (8 files); pytest 186 passed, 2 deselected (51 hook tests).
- Mutation: in a scratch copy with `CFG` dropped from the condition, the hook tests give 8 failed, 43 passed. This matches the developer's report. The 8 failures are the new ASKED entries.
- Offline probes (stdin JSON; the push word is built at runtime). All of these ask: `-c` after `--git-dir=x`, `--git-dir x`, `--exec-path`, `--exec-path=/x`, `-C "a b"`, `-C 'a b'` and `--no-pager`; tab, newline and `git<TAB>-c` separators; a quoted value with spaces; `-c` twice; `-ck=v`; `--config-env=` and `--config-env k=E`; the `env`, `env -i`, `command`, `/usr/bin/git`, `nice`, `time`, `exec`, `nohup`, `xargs`, `FOO=1`, `&&`, `$(...)` and `sh -c` wrappers. These pass, as they should: `git -C d log`, `git -C d status`, `git log -c`, `git -C d log -c` and `git grep -c x`. These block: `git -c k=v -C d <push>`, `git -c k=v <push>` and `git --config-env=k=E <push>`.
- Findings. None is a bounce; the human decides each one under the threat model.
  - F1 (the hook lets these through). Some `-c` forms pass because a global-option token does not match `ARG` or the option list: `git -C a\ b -c ...` (backslash-escaped space), `git -C $'a b' -c ...`, `git -C a"b c" -c ...` (quote inside the token), `git \<newline> -c ...` (line continuation, before or after `-C d`) and `git --super-prefix x -c ...`. The same gaps exist in `PREFIX`: `git -C a\ b <push>`, `git \<newline> <push>` and `git --super-prefix x <push>` pass the hook too. On the push side the deny rule `git * <push>` should still catch the first and third, but nobody has checked that live. There is no `-c` rule in `permissions.ask`, so the `-c` forms rest on the hook alone. The line-continuation form is something an agent could write by accident, so it falls inside the threat model; the others are closer to deliberate evasion. Suggested fix: before matching, run `cmd = re.sub(r"\\\n", " ", cmd)`; widen `ARG` to `(?:\$?'[^']*'|"[^"]*"|(?:\\.|[^\s\\])+)`; add `super-prefix|config-env` to the space-form option list in both `PREFIX` and `CFG`.
  - F2 (the hook lets these through; outside the `-c` AC as written). Config can be injected through the environment with no `-c` at all: `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p GIT_CONFIG_VALUE_0=<push> git p` and `GIT_CONFIG_PARAMETERS="'alias.p'='<push>'" git p`. This is the same inline-alias path that the human decided to close for `-c`. Suggested fix: ask on `\bGIT_CONFIG_(?:COUNT|PARAMETERS|KEY_\d+|VALUE_\d+|GLOBAL|SYSTEM)\b` anywhere in the command.
  - F3 (block becomes ask). `git --config-env k=E <push>` (space form) asks instead of blocking, because `PREFIX` does not take `--config-env` with a separate argument. It still fails closed. The F1 option-list fix also covers this.
  - F4 (the live ask is not shown to a human here). Live, `git -c core.pager=cat log --oneline -1` and `cd <repo> && git -c core.pager=cat log --oneline -1` both ran at once, with no approval prompt or denial visible to the tester. Fed the same strings offline, the hook returns `permissionDecision: "ask"`, and the hook is loaded in this session (the push dry-run below was blocked by it). This session runs in auto mode, so the `ask` was most likely settled by the harness rather than by a human. Every ask rule is affected (`commit`, `rm`, `reset`, `restore`, `checkout`, `config`), not only `-c`. The human should repeat this check in a normal-mode session. If the human must approve these even in auto mode or for subagents, the hook needs `deny` (with a "human runs it" message) rather than `ask`.
- Earlier live checks still hold: the `<push> --dry-run /nonexistent HEAD` probe was blocked by the hook ("Blocked by git policy hook: agents never run git <push> ..."), and `git log --oneline -1` passed.
- Verdict for the added scope: GREEN on the AC as written. Every form the AC lists asks, passes or blocks as specified, and the tests catch a revert. Open for the human: F1 to F4, with F4 the most important.

## Review (reviewer, 2026-11-13, F1-F4 rework)

Verdict: CHANGES REQUESTED (bounce 2 of 2, so the orchestrator stops for the human).

- Gates: ruff exit 0; mypy exit 0 (8 files); hook tests 70 passed (66 policy, 4 commit-msg). Full pytest deferred: 1-minute load was 17-21 (another agent's stress run).
- Regex claim verified. With the tester's suggested ARG, `a"b c"` does not fullmatch ARG, and the CFG form with `-C a"b c"` is not found; the developer's form finds it. The widening implements the F1 AC text ("quotes inside a token"), so it is an implementation change, not a policy change.
- **Blocking: catastrophic backtracking introduced by the new ARG.** `\$?'[^']*'` and the class `[^\s\\'"]` (which also matches `$`) give two parses of every `$'..'` inside the repeated group, so a non-matching token of n `$''` units costs about 2^n. Timed through the hook (machine loaded): n=18 0.21 s, n=20 0.86 s, n=22 3.71 s; a 10k-char token did not finish in 120 s. The old ARG takes 0.02-0.03 s on the same inputs. A command of about 90 characters stalls the hook past its timeout, and what Claude Code does on that timeout (block or pass) is not verified. Fix (one line, tested in scratch): drop the redundant `\$?`, giving `ARG = r"""(?:\\.|'[^']*'|"[^"]*"|[^\s\\'"])+"""` (`$` is then taken by the class and the quotes by the quote branch). All 70 tests pass with it; n=22 and the 10k token take 0.02 s.
- Required with the fix: one regression test that bounds the hook on long adversarial tokens (for example 30 `$''` units, and 40 repeated `-C`, each finishing in under 1 s), so the backtracking cannot come back unnoticed.
- Recommended, pre-existing (not from this rework; for the human or developer to take here or later): the flag branch `-\S+` (and `-(?!c|-config-env)\S+` in CFG) also matches a bare `-C` or `--git-dir` etc., so a run of such options is Fibonacci-exponential (32 repeats: 5.3 s with the old and new ARG alike). Tested in scratch (70 pass, 10k inputs 0.02 s): PREFIX flag branch `-(?![Cc]\s|-{SPACE_OPT}\s)\S+`; CFG flag branch `-(?!c|C\s|-" + SPACE_OPT + r"\s|-config-env)\S+`. Side effect: `-C -c k=v` is then read the way the real CLI reads it (`-c` is the directory).
- Over-matching: none found. These pass: log, status, diff, `-C d log`, `log -c`, `grep -c x`, `show HEAD:'a b'`, `--no-pager log`, `-C 'a b' log -c`, `-C a"b c" log`, `-C a\ b log`, a line continuation then log, `rev-parse --git-path hooks`, `cat .git/config`, `log --grep <push word>`, `help config`, `var -l`.
- Informational forms now denied (all inside the approved F2/F4 decisions; listed for the human): the config subcommand in read-only form (`--get`, `--list`; the former ask covered every config form, so this is the approved deny, not a policy change); any `-c` / `--config-env` read (e.g. `-c core.pager=cat log`); any text naming one of the six listed GIT_CONFIG_ variables, including grep for the name, echo of the variable, and a hermetic global-file prefix on a read (these passed before; F2 says "anywhere in the command", so they fail closed as decided); and Bash text (grep, heredocs) naming commit/rm/reset/restore/checkout/config after the command word is now a deny instead of an ask. Workarounds: `rev-parse --git-path hooks` (shows the effective hooks dir and honours core.hooksPath) and `cat .git/config` both pass; the Grep tool for text.
- commit-msg hook: POSIX sh, `$1` quoted, ERE `AFL-[0-9]{3}` is the same unanchored pattern as `AFL-\d{3}` in require_ticket_in_commit.py; executable bit set. The `#` filter matters: with `-F` and no editor the default cleanup mode is `whitespace`, which keeps `#` lines. The tests use a temp repo and set hooksPath there only.
- Mutation (scratch copy, deleted): F1 reverted (old ARG, no continuation normalisation, no super-prefix/config-env) 7 failed; F2 reverted 3 failed; F3 reverted (config-env not a space option in PREFIX) 1 failed; F4 reverted (ask JSON) 26 failed; commit-msg `#` filter dropped 1 failed. All caught.
- settings.json: unchanged (mtime 2026-11-12 20:38:58). Its `permissions.ask` rules are redundant while the hook runs (the hook's exit 2 wins). They matter only with hooks off (`disableAllHooks`), where they fall back to an ask, which F4 found is settled without a human in auto mode. See question Q1.
- Docs: the README step matches decision (a). The CLAUDE.md diff is one hunk, the section 7 "Working with the git-write policy" bullets, and it matches F4 and the `-F` flow. Ticket fixes to make with the rework: (1) "Human live checks (tester, 2026-11-12)" step (b) and the "Tester's live-check list" still expect an approval prompt; mark them superseded by the F4 live check. (2) Known gaps: "Now asks via CFG" should say denied. (3) The latest human command list (2026-11-12) lacks `.githooks/commit-msg`, `tests/test_commit_msg_hook.py`, `README.md` and `CLAUDE.md` (both diffs are AFL-015 only); write one consolidated list.
- Questions for the human (not decided here): Q1, change the settings.json `permissions.ask` rules to `deny` for defence in depth when hooks are off, or leave them (F4 said "not edited here")? Q2, keep read-only config (`--get`, `--list`) denied, or carve it out? The reviewer leans keep: workarounds exist and a carve-out adds parsing. Q3, take the pre-existing `-C` backtracking fix in this ticket?

## Review (reviewer, 2026-11-13, re-review after bounce 2)

Verdict: APPROVED to testing. Decisions (a) and (b) are implemented exactly, and the requested ticket-text fixes are done. Before the commit, the orchestrator must make two list corrections (R1, R2), which are outside the reviewer's write scope. One new finding (F5) is for the human. None of these is a bounce.

- Patterns (item 1). `ARG` is exactly `(?:\\.|'[^']*'|"[^"]*"|[^\s\\'"])+` (decision (a)). The bare-flag branch is `-(?![Cc]\s|-{SPACE_OPT}\s)\S+` in `PREFIX` and `-(?!c|C\s|-" + SPACE_OPT + r"\s|-config-env)\S+` in `CFG` (decision (b)). Read-only config is still denied (decision (c)). `.claude/settings.json` is unchanged, mtime 2026-11-12 20:38:58 (decision (d); not counted as a defect).
- Hostile timing (the reviewer's own inputs, about 10k chars each, run through the hook as a subprocess). Thirty classes took 0.014-0.021 s each: `$''`, unclosed `$'`, mixed `$'a'\x"b"`, unclosed `"` / `'` runs, backslash runs, `\'`, and repeated `-C`, `-c`, `-C a`, `--git-dir`, `--config-env` and `--config-env k=E`. Also `-C -c` alternating, a mixed option soup, runs of continuations, `-C \<newline> d`, 10k spaces, a tab/newline mix, quoted flag values and runs of the GIT_CONFIG_ name. No exponential path remains. One quadratic case is left (not exponential): the command word repeated inside option arguments, because every `git` is a new search start that rescans the rest. `git -C git -C ...` takes 0.16 s at 5k, 0.61 s at 10k, 2.36 s at 20k and 9.2 s at 40k (x4 per doubling); `git -C '` repeated takes 0.30 s at 10k. **Worst at 10k chars: 0.60 s.** Real commands are under 1k chars (<0.02 s). A hook timeout needs about 100k chars of deliberate repetition, which is outside the threat model. Noted, not a bounce.
- Time-limit tests are meaningful (item 3). Scratch mutants (deleted): restoring `\$?` in ARG gives 3 failures (77, 311 and 10013 chars); restoring the old flag branches (`-\S+`, `-(?!c|-config-env)\S+`) gives 3 failures (103, 907 and 3007 chars); the current code passes 72. Any 2^n (or Fibonacci) regression, however small its constant, sends the 100-unit `$''` case (311 chars) and the 300 `-C` case to the 10 s timeout. A looser bound therefore cannot hide one. `returncode == 0` makes all three regexes run to the end. The 1 s bound includes interpreter start-up (about 0.015 s here), which leaves ample margin against flakes.
- Over-matching: none (item 2). Each of 42 allowed forms was run bare, after `cd /x &&` and after `FOO=1` (126 probes); all pass. They include log, status, diff, `-C d log`, `log -c`, `grep -c x`, `show HEAD:'a b'`, `-C a"b c" log`, `-C 'a b' log -c`, `-C a\ b log`, `-C $'a b' log`, a continuation then log, `help config`, `rev-parse --git-path hooks`, `--no-pager log`, `log --grep <push word>`, `var -l`, `blame -C f`, `show -c HEAD`, and `-C -c log` (directory `-c`, which is how the CLI reads it). `cat .git/config`, a `GIT_CONFIG_NOSYSTEM=1` prefix on a log, and words like `mygit` or `git-commit` also pass.
- F1-F4 still deny. Each form was run bare and in both wrappers. The 27 deny forms all exit 2 with the F4 message: commit, rm, reset, restore, `checkout --`, config (including `--get` and `--list`), every F1 quoting and continuation form, `--super-prefix`, `--exec-path=/x -c`, `-C "a b" -c` and `--git-dir "a b" -c`. The 15 push forms all get the push message, including F3 `--config-env k=E <push>`, `-C $'a b'`, `-C a"b c"`, a continuation and `-c k=v -C d`. The 4 GIT_CONFIG_ injections (F2) are denied.
- **F5 (new, for the human; not a bounce).** The hook does not parse escaped quotes inside a quoted token, or a quoted option value that contains a space. So these pass the hook: `-C $'a\'b' -c k=v log`, `-C "a\"b" -c k=v log` and `--exec-path="a b" -c k=v log`, and as pushes `-C $'a\'b' <push>`, `-C "a\"b" <push>` and `--git-dir="a b" <push>`. The push forms should still hit the rule-layer push deny rules, but that was not checked live. These gaps are pre-existing: the pre-bounce ARG lets all six through too. They are closer to deliberate evasion than to accident. Decision (a) fixed ARG exactly, so changing it is the human's call. Tested fix (scratch copy, deleted): `ARG = r"""(?:\\.|\$'(?:\\.|[^'\\])*'|'[^']*'|"(?:\\.|[^"\\])*"|\$(?!')|[^\s\\'"$])+"""`, and both bare-flag branches end in `{ARG}` instead of `\S+`. Each unit then has one parse: `$'` is taken only by the ANSI-C branch, and a backslash inside `$'..'` or `".."` is taken as an escape. With the fix, 72 tests pass, every list above has 0 mismatches, all six forms deny or block, and the worst 10k timing is unchanged (0.64 s).
- Ticket text (item 4) is fixed:
  - live check (b), "Updated live checks for F4" and the tester list all expect DENY;
  - Known gaps says denied;
  - there is one consolidated list, and the earlier lists are removed from the Log. The 2026-11-12 "pending (human)" Log line still has two inline commands, but it is marked superseded.
- Consolidated list (item 5), checked against `git status`, `git ls-files` and `git diff`:
  - Corrected by the reviewer (orchestrator fact check): the pyproject line is now a plain add. `git diff pyproject.toml` has one hunk, and `git diff --cached` is empty.
  - Every listed path exists.
  - The three untrack targets are tracked today. For DS_Store and headroom, `git ls-files` lists exactly `.DS_Store`, `docs/.DS_Store` and `.claude/.headroom_wrap_settings.lock`.
  - After untracking, `git check-ignore --no-index -v` matches `.gitignore:12` (`.DS_Store`) for both DS_Store files, and `.gitignore:8` (`.claude/.headroom_wrap_*`) for the lock and for marker.json.
  - `settings.json`, `.githooks/commit-msg` and the hooks are not ignored.
  - Nothing from another ticket is swept in. `.claude/agents/tester.md`, `tickets/backlog/INDEX.md`, the executor/fuzzer files and other tickets' files are not listed. README.md and CLAUDE.md each have one hunk, and both are AFL-015's.
  - **R1 (required before the commit).** The list misses the deletion of the tracked `tickets/backlog/AFL-015-track-claude-hooks-in-git.md` (status ` D`). Without it, the commit adds the new copy and HEAD keeps the old backlog copy. Add `git add tickets/backlog/AFL-015-track-claude-hooks-in-git.md`, which stages the deletion.
  - **R2 (required before the commit).** The ticket is now at `tickets/testing/AFL-015-track-claude-hooks-in-git.md`. The list's `tickets/review/...` add line must name the ticket's location at commit time.
  - Nit: the sentence "no `.DS_Store` is listed" means that no add of one is listed. The untrack line does list both.
- Gates: ruff exit 0; mypy exit 0 (8 files); `pytest tests/test_git_policy_hook.py tests/test_commit_msg_hook.py` exit 0, 76 tests (72 policy, 4 commit-msg). The full suite was not run (orchestrator instruction: another reviewer is timing).

## Review (reviewer, 2026-11-13, re-review of the F5 and (d) change)

Verdict: APPROVED to testing. This is a human-directed change, not a bounce (the count stays 2 of 2). F5 and (d) are implemented exactly, and each new test pins its fix. The new findings F6-F8 are pre-existing gaps (the pre-F5 hook has each of them too) and are for the human; none is a bounce. F6 is the one worth taking before the commit.

- F5 pattern. `ARG` is character-for-character the reviewer's tested form. Both bare-flag branches end in `{ARG}` (PREFIX `-(?![Cc]\s|-{SPACE_OPT}\s){ARG}`; CFG `-(?!c|C\s|-SPACE_OPT\s|-config-env)` + ARG). Each ARG unit has exactly one parse, because its first character picks the branch: `\` escape, `$'` ANSI-C, `'`, `"`, `$` not followed by `'`, or any other character.
- The tests pin each fix (scratch mutants, deleted):
  - pre-F5 hook (old ARG and `\S+` branches): exactly the 7 new policy tests fail and 76 pass, which confirms the developer;
  - ARG reverted alone: the 5 escaped-quote forms fail;
  - flag branches reverted alone: the 2 `="a b"` forms fail;
  - `$` put back into ARG's last class: 5 hostile tests fail (the 77-, 311- and 10013-char `$''` inputs and both `$'\'` inputs, 10011 and 171 chars), so the new hostile inputs also guard the `$` exclusion.
- Quoting forms the new ARG reads correctly; each is blocked as a push or denied: `-C $"a b"`, `-C $"a\"b"`, adjacent pieces `'a'"b"$'c'd`, adjacent pieces with escapes `a$'b\'c'"d\"e"`, `"a b"\ c`, `'a\'` (the backslash is literal in single quotes), `"a\\"`, `$'a\\'`, `\$'x'`, a lone `$`, `a$`, `--exec-path="a b" --no-pager -c k=v log`, `--namespace='a b'` then commit, and a continuation before config. Over-match: none. These pass: `-C "a\"b" log`, `-C $'a\'b' log`, `--git-dir="a b" log`, `log --grep="a b"`, `show 'HEAD:a b'`, `-C d log -c` and `-C $'a b' status`.
- Hostile timing: 21 classes of about 10k chars each, run through the hook, at load about 2.1. They include unclosed `$'`, `$'\'` and `"\` runs, `$"`, `$""`, `\$'`, `$$`, `$\`, `'$'`, mixed units, `-x"a b"` flags, `--git-dir=` runs, `$(` and backtick runs, `-C -c`, `--config-env k=E`, `-p$'a'` and continuation runs. Each takes 0.028-0.034 s. The only slow class is the known quadratic one, where the command word repeats inside option arguments: 1.2 s for `-C <git>` x1428, and 0.6 s for the unclosed `'` variant. The pre-F5 hook gives the same (1.16-1.20 s), so F5 adds no cost. Real commands are under 1k chars. No exponential path remains.
- Bypasses tried. Each passes the hook (exit 0), and each also passes the pre-F5 hook:
  - **F6 (medium; an agent could write this by accident, so it is inside the threat model).** Unquoted command substitution with a space inside it, used as a global-option argument. ARG reads `$(` as `$` plus ordinary characters and ends the word at the inner space. So `-C $(git rev-parse --show-toplevel)` followed by push, by commit, or by `-c k=v log` passes the hook. This is the common "repo root" idiom. `-C $(echo d)`, a backtick substitution with a space, and `${X:-a b}` pass the same way. The quoted form `-C "$(...)"` is caught. At the rule layer, `Bash(git * push)` and `Bash(git * commit *)` should catch the push and verb forms. That was not checked live, and how Claude Code matches rules against `$(...)` is not verified. The `-c` form rests on the hook alone.
    - Tested fix (scratch, deleted): add the branches `\$\((?:[^()]|\([^()]*\))*\)`, `\$\{[^}]*\}` and a backtick-quoted branch to ARG; change `\$(?!')` to `\$(?![('{])`; exclude the backtick from ARG's last class.
    - Result: 83 tests pass; the `$(...)`, backtick and `${..}` forms deny or block; `-C $(git rev-parse --show-toplevel) log`, `-C $(echo a) status`, a backtick `pwd` before diff, and `log --format='%h $(x y)'` still pass; the worst 10k timing is unchanged (1.3 s, the quadratic case).
    - Suggested tests: the three rev-parse forms above.
  - **F7 (low; looks deliberate).** A line continuation inside a word. Bash removes a backslash-newline entirely, but the hook replaces it with a space. So `-C a\<newline>b -c k=v log`, `-C a\<newline>b` then push, `pu\<newline>sh` and `com\<newline>mit -m x` pass. One-character fix, tested together with F6: `re.sub(r"\\\n", "", cmd)`. All 83 tests pass, and the four forms deny or block.
  - **F8 (low; deliberate evasion, in the same class as the quoted command word under Known gaps).** A quoted or escaped subcommand or `-c`: `"push"`, `pu''sh`, a backslash before push, `'commit'`, `'-c'`, `"-c"` and `$'\x2dc'`. Also a command word produced by substitution: `$(command -v git)` then push. Recommendation: widen the Known-gaps line from a quoted command word to "a quoted or escaped command word, subcommand or option, or a command word produced by substitution". No code change.
  - Informational: newer git documents `--attr-source=<tree-ish>`, and `SPACE_OPT` lacks it. If git.c also takes the space form, then `--attr-source HEAD` followed by push, commit or `-c` would pass. This is not verified: the local git is Apple 2.39.5, which rejects the option entirely.
- settings.json:
  - It is valid JSON (`json.tool` OK). `permissions` holds only `deny`, with 21 rules: the three push rules (unchanged) and then the three patterns for each of commit, rm, reset, restore, checkout and config. There is no `ask` key.
  - The hooks block matches the earlier description exactly: one PreToolUse entry with matcher Bash, and three command hooks (require_ticket_in_commit, gate_ticket_done, git_policy), each `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/<name>.py"` with `onFailure: "block"`. There are no absolute paths.
  - The over-match is recorded under Known gaps, as decided.
  - Text fix (reviewer): the AC "Tracked commit-msg hook" still said "`.claude/settings.json` is unchanged". It is now annotated as superseded by AC (d).
- Consolidated list, checked against `git status`. HEAD's AFL-028 commit is 8618c7c, and nothing is staged (`git diff --cached` is empty).
  - Every AFL-015 path is listed: the 3 hooks, settings.json, the 2 commands, `.githooks/commit-msg` (mode 755), the 2 test files, `.gitignore`, README.md, CLAUDE.md, pyproject.toml, the backlog-copy deletion (R1; status ` D`) and the ticket. The 3 untracks are listed too; exactly `.DS_Store`, `docs/.DS_Store` and `.claude/.headroom_wrap_settings.lock` are in the index.
  - README.md, CLAUDE.md and pyproject.toml each have exactly one hunk, and each hunk is AFL-015's: the `core.hooksPath` step, the section 7 git-write bullets, and the `extend-exclude` entry with its comment.
  - Nothing unrelated is listed. Left out: `.claude/agents/tester.md`, `tickets/backlog/INDEX.md` (its AFL-015 lines are grooming and freeze-set text, mixed with other tickets' lines), `docs/adr/0005-...`, `src/fuzzer/fuzzer.py`, `tests/test_executor.py`, `tests/test_fuzzer.py`, `tests/fixtures/tlv_parser_asan_memcpy.txt` and the other tickets.
  - After the list, the only change left under `.claude/` is `.claude/agents/tester.md` (grooming commit). The ignored set is `settings.local.json`, plus the lock once it is untracked.
  - R2: the reviewer updated the list's ticket line to `tickets/testing/...` to match the move made with this approval.
- Gates: ruff exit 0; mypy exit 0 (8 files); `pytest tests/test_git_policy_hook.py tests/test_commit_msg_hook.py` 87 passed (83 policy, 4 commit-msg). The full suite was not run (orchestrator instruction).

### Addendum (reviewer, 2026-11-13, F6/F7 fix)

Verdict: the code is correct. **R3 (required before the commit, test-only):** the one new ambiguity guard is not pinned by any test. The ticket stays in testing/; the human decides whether R3 is taken now. Not a bounce.

- ARG is unambiguous per unit. The first character picks the branch: `\` escape, `$'`, `'`, `"`, `$(`, `${`, a backtick, `$` before anything except `(`, `'` or `{`, and any other character (the last class excludes `$` and the backtick). Inside each branch the alternatives are disjoint: `[^()]` versus `\(`, `\\.` versus `[^`\\]`.
- Timing: 21 classes of about 10k characters each through the hook, all at most 0.04 s. They include unclosed `$(`, `${` and backtick runs, `$((`, `$(a(b)`, `$( (`, `$(())`, closed `$(a)`, `${a}`, `$(a b)` and `${a b}` runs, a backtick containing `\`, `$(${`, `$({)`, `$(` followed by 5k spaced words, `$(e$(e` runs, `)` runs, and `-C $(` repeated with the command word. The only slow input is the known quadratic case (`-C <git>` repeated): 1.3 s, unchanged.
- **R3.** The exclusion in `\$(?![('{])` is what keeps `$(..)` and `${..}` to one parse. Mutant `\$(?!')`: all 106 policy tests pass, but closed runs are 2^n (`$(a)` x20: 1.9 s; `${a}` x20: 1.7 s, against 0.03 s now). None of the 5 new hostile inputs is closed (`$(`, `${` and `$(a (b` are unclosed), so none can see it. Fix, tested: add `"$(a)" * 2500`, `"${a}" * 2500` and `"$(a)" * 40` to HOSTILE. The mutant then fails all 3 (two hit the 10 s timeout); the current code passes all 18 hostile tests in 0.66 s.
- Pinning (scratch mutants, deleted): ARG back to the F5 form fails the 12 substitution tests; continuation back to a space fails the 3 continuation tests (15 in all, which confirms the developer); a backtick back in the last class fails 1 hostile test (the backtick run). The 3 read-only controls pass on every version.
- Bypasses tried. Blocked or denied: `-C $(echo \))`, `${a:-}}`, `${a:-${b}}`, `${X:-$(a b)}`, a backtick with an escaped backtick, a backtick `a b` before commit, `$(( 1 + 2 ))`, `$( (cd x; pwd) )`, two substitutions then `-c`, a substitution spanning a newline, a continuation inside a substitution, and an unclosed `$(` followed later by the command word and push (the search restarts at every command word, so an unclosed `$(` hides nothing after a later command word; and bash rejects an unclosed `$(` anyway). Passing, as they should: `$(...)` containing the push or commit word before `log`, `-C $(<git> rev-parse --show-toplevel) status`, `log --format='%h $(x y)'`, `${X:-a b} diff`, a backtick `pwd` before log.
- **Residual (low; deliberate-looking; now under Known gaps):** a substitution the branch cannot close (nesting deeper than one level, a quoted or escaped paren, a `case` `)`) makes the word unreadable, so the hook misses the subcommand after it. One small regression: the space-free `-C $(echo$(echo$(pwd)))` was caught by the F5 ARG (read as plain characters) and now passes. A fallback branch `\$(?=[({])(?!<subst>|<brace>)` restores it (106 pass) but adds a quadratic cost (unclosed `${` x5000: 0.22 s). Not recommended; documenting is enough.
- Ticket text: the F6/F7 CLOSED line, the F8 and `--attr-source` lines, and the developer's Log claims (15 bypass tests fail on the old hook; 110 pass) are accurate. Two reviewer edits: the residual-F6 Known-gaps line, and "not checked live" on the F8 claim that the settings rules miss quoted forms.
- Gates: ruff exit 0; mypy exit 0 (8 files); `pytest tests/test_git_policy_hook.py tests/test_commit_msg_hook.py` 110 passed. The full suite was not run.

## Tester (2026-11-13, clean-copy verification after F5, (d), F6, F7 and R3)

Verdict: PASS (GREEN) on the clean copy. The ticket is ready to close once the human commit and the human live checks are done. No defects were found, and no bounce is raised (the count stays 2 of 2).

- **Clean copy.** `git archive HEAD` (8618c7c) was unpacked into scratch. On top of it went the working-tree files that the consolidated list stages: `.gitignore`, the 3 hooks, `settings.json`, the 2 commands, `.githooks/commit-msg` (mode 755 kept), the 2 hook test files and this ticket at `tickets/testing/`. The untrack and delete steps were applied by leaving the files out: `.claude/.headroom_wrap_settings.lock`, `.DS_Store`, `docs/.DS_Store` and the backlog copy of this ticket. The README.md, CLAUDE.md and pyproject.toml diffs were applied with `patch`; each is one hunk, and each patched file is byte-identical to the working tree. `targets/bin` was copied read-only from the repo. `make` was a no-op shim on PATH, so nothing was built. The scratch copy was deleted afterwards.
- **(a) Gates (repo `.venv`, Python 3.12.9). PASS.** `ruff check .` exit 0. `mypy src` exit 0 (8 files). Full `pytest`: 210 passed, 1 deselected (`slow`), 0 skipped, in 14.3 s. The `needs_clang` tests ran against the copied binaries.
- **(b) Hook tests, 3 runs. PASS.** `tests/test_git_policy_hook.py` and `tests/test_commit_msg_hook.py` gave 113 passed in each run (109 policy, 4 commit-msg), in 3.87 s, 3.84 s and 3.78 s. All 18 hostile inputs took at most 0.04 s per test in pytest. One direct pass of each input through the hook: the slowest was `"\"` x3334 (10013 chars), at 0.033 s. All 18 fall in 0.032-0.033 s, which is interpreter start-up, and each exits 0. The load average was about 2.
- **(c) Hook probes (JSON on stdin, scratch hook). PASS: 70 of 70 as expected.**
  - Push blocked, exit 2 with the push message (9 probes): bare, `--dry-run /nonexistent HEAD`, after `cd /x &&`, after `FOO=1`, `/usr/bin/git`, `sh -c`, `-C d`, `--config-env k=E`, and `-c k=v -C d`.
  - Denied, exit 2 with the "human runs this git command" message (12 probes): commit `-m` and `-F`, rm `--cached`, reset `--soft`, restore, checkout `--`, config `--get` and the alias form, `-c core.pager=cat log`, `--config-env=k=E log`, the GIT_CONFIG_COUNT/KEY/VALUE injection, and `true && git -C x commit --dry-run ...`.
  - F5 (7 probes, all denied or blocked): `-C $'a\'b'`, `-C "a\"b"` and `--exec-path="a b"`, each before `-c`; `-C "a\"b"` before commit; and `$'a\'b'`, `"a\"b"` and `--git-dir="a b"` before the push.
  - F6 (7 probes, all denied or blocked): `-C $(git rev-parse --show-toplevel)` before the push, before commit and before `-c`; `${X:-a b}` and a backtick `echo a b` before the push; `$(echo d)` before commit; and `$(echo $(pwd))` before `-c`.
  - F7 (6 probes, all denied or blocked): `a\<nl>b` before `-c` and before the push, `pu\<nl>sh`, `com\<nl>mit`, `git \<nl>` before the push, and `-C d \<nl> -c`.
  - Read-only controls, exit 0 with empty stderr (24 probes): status, `status -sb`, log, `diff --cached --stat`, `-C d log`, `log -c`, `grep -c x`, `show HEAD:'a b'`, ls-files, check-ignore, `rev-parse --git-path hooks`, `cat .git/config`, `log --grep <push word>`, the rev-parse substitution before status, `$(echo a)` status, a backtick `pwd` before diff, `log --format='%h $(x y)'`, `-C "a\"b" log`, `-C $'a\'b' log`, `--git-dir="a b" log`, `a\<nl>b log`, `cd /x && FOO=1 git log`, `git archive HEAD | tar`, and `mygit-commit`.
  - Malformed stdin, exit 0 (5 probes): empty input, non-JSON, `[]`, a non-string command, and a null `tool_input`.
- **(d) settings.json. PASS.**
  - It is valid JSON (`json.tool` OK). The top-level keys are `permissions` and `hooks`, and `permissions` holds only `deny`, with no `ask` or `allow` key.
  - The deny list has exactly 21 rules, all unique. They equal, in order, `Bash(git <v> *)`, `Bash(git * <v>)` and `Bash(git * <v> *)` for push, commit, rm, reset, restore, checkout and config.
  - There is one PreToolUse entry, matcher `Bash`, with three `command` hooks. Each is `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/<name>.py"` with `onFailure: "block"`, and each of the three paths exists in the clean copy.
  - No `/Users/` path appears in `settings.json`, `.claude/`, `.githooks/`, `.gitignore`, `pyproject.toml` or the two test files.
- **(e) Commit list against the real `git status` (HEAD 8618c7c, unchanged from start to end; nothing staged). PASS.**
  - Every AFL-015 change is listed: ` M .gitignore`, README.md, CLAUDE.md and pyproject.toml; ` D` for the backlog copy; `??` for the 3 hooks, settings.json, the 2 commands, `.githooks/commit-msg`, the 2 hook tests and the testing/ ticket. The 3 untracks are listed too, and the index holds exactly `.DS_Store`, `docs/.DS_Store` and `.claude/.headroom_wrap_settings.lock`.
  - Nothing from another ticket is listed. These files are left out, correctly: `.claude/agents/tester.md`, ADR-0005, `src/fuzzer/fuzzer.py`, `tests/test_executor.py`, `tests/test_fuzzer.py` and `tests/fixtures/`; AFL-007's two ticket paths, AFL-027's done ticket, the modified AFL-008/010/011/013/016/018 tickets, `INDEX.md`, and AFL-024/025/026/029. Their diffs mention AFL-015 or `.DS_Store` only in other tickets' grooming text, with no AFL-015 deliverable in them. Without them the clean copy is self-consistent: all gates pass.
  - After the list, `.claude/` holds only `M .claude/agents/tester.md` (the grooming commit). `check-ignore --no-index` matches `.gitignore:12` for both `.DS_Store` files (and `tests/.DS_Store`), `.gitignore:8` for the lock and `marker.json`, `:9` for `settings.local.json`, `:17` for `results/x/y.bin`, the `:18` negation for `results/.gitkeep`, and `:24` for `.serena/`. The listed new files are not ignored. `.prettierignore` at HEAD has `**/*.md`.
  - No discrepancy was found.
- **(f) Human live check of the settings.json deny rules. PASS (listed).** It is a human step in AC "(d) settings.json denies": a normal-mode session with `"disableAllHooks": true`, then `git -C x commit --dry-run -m "AFL-015 live check"`, expecting a settings deny. Afterwards the line is removed, the session restarted, and the file checked with `cat`. The tester cannot run it from inside a session.
- Nit (not a defect): two Log lines in this ticket name `/Users/...` in prose (a grep pattern, and the reviewer's note on `settings.local.json`). They are documentation, not paths that any code uses. AFL-028's done ticket, which is in HEAD, has the same.
- **Still open (human, not tester-runnable):**
  - the consolidated commit, with `git config core.hooksPath .githooks` run once per clone;
  - live checks (b) and (e), the F4 updates, the (d) `disableAllHooks` check and the commit-msg check (c);
  - after the commit, the `git ls-files` ACs, the fresh-clone ruff, commit-block and done-gate checks, the Finder-touch `git status --porcelain` check, the `.claude/` inventory (after the grooming commit too), and confirming that origin is unchanged until a manual push.

## Close (crew-lead, 2026-11-13)

Verdict: DONE, with the human-only items below open. The ticket is closed on the working tree; the
commit-dependent ACs stay unticked until the human runs them.

DoD, item by item:
- All acceptance criteria verified on a clean checkout: MET for every AC an agent can check
  (tester clean copy, (a)-(f) PASS). The ACs that need the commit (`git ls-files`, fresh clone,
  inventory, Finder touch, origin unchanged) and the live-session checks are the human's (below).
- Tests meaningful and green: MET. 113 hook tests (109 policy, 4 commit-msg); every fix is pinned
  by a scratch mutant (F1-F7, R3, the hostile timing inputs, the commit-msg `#` filter).
- `ruff` / `mypy` / `pytest` pass: MET. Tester clean copy: ruff 0, mypy 0 (8 files), pytest 210
  passed, 1 deselected. The `gate_ticket_done.py` hook ran all three on the live tree for the close
  move and let it through.
- Validity checklist: n/a (process tooling, not an experiment).
- Reproducibility confirmed: MET. A fresh clone gets the gates once the commit lands; the one
  per-clone step (`core.hooksPath`) is in README.md.
- Ticket Log complete: MET (this close line added).
- Commit references the ticket id: OPEN (human). The commit uses the `-F` flow with an `AFL-015`
  message, per AC "(d) AFL-015's own commit uses this `-F` flow".

DoD open items (human only; agents are denied these):
1. The consolidated commit: run the "Human commit list (consolidated)" above from the repo root,
   ending in `git commit -F <message file>`; the orchestrator writes the message file.
2. `git config core.hooksPath .githooks`, once per clone (this clone and the fresh-clone check).
3. Human live checks, as listed in this ticket: (b) commit denied with no prompt; (e) a
   `settings.local.json` allow cannot re-enable push, then `cat .claude/settings.local.json` to
   confirm the allow line is gone; the F4 updates ("Updated live checks for F4"); the (d)
   `disableAllHooks` settings-deny check (the commit form, and the F6 push form
   `git -C $(git rev-parse --show-toplevel) push --dry-run /nonexistent HEAD`: denied, no prompt,
   not run), then remove the line, restart and `cat` the file; and the
   commit-msg check (c) (rejected without id, accepted with `AFL-015`, throwaway undone).
   Update (lead decision, 2026-11-14): (c), (e) and the (d) `disableAllHooks` check are dropped
   (see Known gaps); (b) and the F4 commit and `-c` parts were checked live on 2026-11-14 (see
   those items); the push probe and fresh-clone check were not performed.
4. After the commit: the `git ls-files` ACs, the fresh-clone ruff, commit-block and done-gate
   checks, the Finder-touch `git status --porcelain` check, the `.claude/` inventory (after the
   grooming commit too), and confirming that origin is unchanged until a manual push.

## Log

- 2026-11-07 — created (req-engineer) from AFL-001 tester finding
- 2026-11-07 — added .prettierignore AC after Prettier format-on-save reformatted AFL-011 (human decision) (req-engineer)
- 2026-11-07 — batch grooming: decision — exclude `.claude/hooks` from ruff via a commented `pyproject.toml` entry, not fix (hooks are process tooling); ruff AC adjusted to that branch. AFL-021 merged in (its `.DS_Store` ACs appended; module += docs/.DS_Store). The human performs all `git rm --cached` steps (human decision) (req-engineer)
- 2026-11-07 — review fix: added AC that `.gitignore` contains `.serena/` (already present at line 22) (human decision) (req-engineer)
- 2026-11-07 — review fix: added AC that `.gitignore` ignores `results/` wholesale with `results/.gitkeep` still tracked, tested via `git check-ignore results/x/y.bin` and `git ls-files results/.gitkeep` (human decision) (req-engineer)
- 2026-11-07 — review fix: `results/` rule specified as `results/*` + `!results/.gitkeep` (a bare `results/` cannot re-include a file); test adds `git check-ignore -q results/.gitkeep` exits 1 (human decision) (req-engineer)
- 2026-11-07 — review fix: no-auto-push AC (human decision) (req-engineer)
- 2026-11-12 — root `.DS_Store` is tracked too: added AC that the human runs `git rm --cached .DS_Store` (root) in addition to `docs/.DS_Store`; module line and test approach updated (human decision) (req-engineer)
- 2026-11-12 — developer: working-tree part done. `.gitignore` (blanket `.claude/` removed; `.claude/.headroom_wrap_*`, `.claude/settings.local.json`, `.DS_Store`, `results/*` + `!results/.gitkeep`; `.serena/` kept), `pyproject.toml` (`extend-exclude = [".claude/hooks"]` + comment), `.prettierignore` was NOT changed (see restore note below). `ruff check .` exits 0; without the exclude (`--isolated`) the hooks give 9 errors, so the exclude is what keeps it green. `git check-ignore -v`: `.DS_Store`, `docs/.DS_Store` (need `--no-index`, both tracked), `tests/.DS_Store`, `.claude/settings.local.json`, `results/x/y.bin` each print a rule; `results/.gitkeep` and `.claude/settings.json` exit 1. Both `.DS_Store` paths covered by the one unanchored rule and by the two human `git rm --cached` steps below.
- 2026-11-12 — developer: hooks run by stdin payload: `require_ticket_in_commit.py` exit 2 for "no ticket id", 0 for "AFL-015 msg". `gate_ticket_done.py` in a throwaway copy (deleted): exit 0 clean, exit 2 with one failing test. Live repo currently fails `mypy src` (executor.py:70, another ticket's WIP), so the done-gate would block any done-move right now. Prefers project `.venv` (already true); `grep /Users/` over settings.json, hooks, .gitignore, .prettierignore, pyproject.toml finds nothing.
- 2026-11-12 — developer: no-auto-push check (read-only): `.git/hooks/` only `*.sample`; aliases local none, system none/unreadable (no /etc/gitconfig), global `ci co st br cat cp` (commit/checkout/status/branch/show/cherry-pick), none pushes; no workspace `.vscode/`; Code user settings.json only `parallels-desktop.git.path`, Cursor settings.json absent; no `postCommitCommand`/autopush/sync. `git status -sb` shows `main...origin/main` (not ahead). Post-commit confirmation of origin unchanged is for the tester.
- 2026-11-12 — pending (human), run from repo root: `git rm --cached .claude/.headroom_wrap_settings.lock` (checked: only the `.lock` is in the index today; if `marker.json`/`owners.json` appear later in `git ls-files .claude | grep headroom`, add them), `git rm --cached .DS_Store docs/.DS_Store`, (superseded by the corrected list in the next entry). Then commit with an `AFL-015` message.
- 2026-11-12 — for tester, post-commit: ACs left unticked need the commit: `git ls-files` for settings.json/hooks/.prettierignore/headroom/DS_Store/results/.gitkeep; fresh-clone ruff, commit-block and done-gate; Finder-touch `git status --porcelain`; origin unchanged after commit. Moved to review (developer)
- 2026-11-12 — reviewer: CHANGES REQUESTED (bounce 1). Working-tree ACs checked: `.gitignore` targeted `.claude/` rules, `.DS_Store`, `.serena/`, `results/*` + `!results/.gitkeep` all met (`git check-ignore`: `.gitkeep` exit 1, `results/x/y.bin` printed, `.DS_Store`/`docs/.DS_Store`/`tests/.DS_Store`/`settings.local.json`/`.headroom_wrap_settings.lock` matched, `settings.json` exit 1; `git ls-files results/.gitkeep` lists it). `pyproject.toml` exclude + comment present; `ruff check .` exit 0, and `ruff check .claude/hooks/*.py` under project config gives 9 errors, so green is due to the exclude, as decided. `settings.json` and both hooks: no absolute paths, user names or secrets (only `$CLAUDE_PROJECT_DIR`); `git grep` for `/Users/` over tracked files is empty. `settings.local.json` holds `/Users/shinobi07/.pyenv/...` and is correctly ignored. Commit hook: exit 2 for "no ticket id", 0 for "AFL-015 msg". Index: only `.claude/.headroom_wrap_settings.lock` (headroom) and only `.DS_Store`, `docs/.DS_Store` (DS_Store) are tracked; `tickets/.DS_Store` on disk is untracked and ignored. **Blocking:** `.prettierignore` is not new; it is tracked since HEAD, and the working-tree change deletes its two rationale comment lines (`# Tickets, PRD and ADRs carry pre-registered text; ...`). The AC is already met by HEAD, so this is an unrequested regression, and the pending `git add .prettierignore` would commit it. Fix: restore `.prettierignore` to HEAD content (empty diff) and drop it from the `git add` list. **Decision for human (not blocking):** with the blanket rule gone, `.claude/commands/groom-backlog.md` and `.claude/commands/run-backlog.md` newly show as untracked; CLAUDE.md §7 names `/run-backlog` as a driver, so a fresh clone lacks it. Either add both in this commit (fits the ticket goal) or ticket them separately. `.claude/agents/tester.md` is modified by another ticket; do not stage it here. Hooks lack the exec bit (EXE001) but are run as `python3 <path>`, so no effect. (reviewer)
- 2026-11-12 — developer, review bounce 1: `.prettierignore` is already tracked at HEAD with `**/*.md` (the AC was already met; my earlier rewrite dropped its two comment lines). Restored from `git show HEAD:.prettierignore`; `git diff --quiet -- .prettierignore` exits 0. Corrected pending (human) commands:
  (command list removed 2026-11-13: superseded by "Human commit list (consolidated)")
- 2026-11-12 — reviewer: re-review after bounce 1, APPROVED. `.prettierignore` is back to its HEAD content: `git diff --quiet -- .prettierignore` exits 0, and the comment lines and `**/*.md` are present. The corrected human command list above is complete and supersedes the earlier "pending (human)" line, which listed `.prettierignore`. Unchanged since the first review: `.gitignore` and the `pyproject.toml` diffs; `ruff check .` exits 0. Every working-tree AC is met. Still open for the tester after the human commit: `git ls-files` checks, the fresh-clone ruff, commit-block and done-gate checks, the Finder-touch `git status --porcelain` check, and confirming origin is unchanged after the commit. The human still has to decide on `.claude/commands/groom-backlog.md` and `run-backlog.md`; this does not block the ticket. Moved to testing (reviewer)
- 2026-11-12 — scope added by the human, not a bounce (the bounce count stays at 1): three ACs under "Added scope": the two slash-command files are tracked (this settles the reviewer's open decision: add them in this commit); the `.claude/` inventory is clean after the commit, with the ignored set exactly `.claude/settings.local.json` and `.claude/.headroom_wrap_*`, checked after both this commit and the grooming commit that carries `.claude/agents/tester.md`; and `.claude/settings.json` denies `git push` and requires human approval for `git commit`, `git rm`, `git reset`, `git checkout --` and `git restore`, with tests (a)–(d), mechanism left to the architect. Status testing → in-progress, file moved to `tickets/in-progress/` (human decision, 2026-11-12) (req-engineer)
- 2026-11-12 — human command list, superseding the bounce-1 list above (adds the two slash-command files; human decision, 2026-11-12). Run from the repo root, after the developer finishes the added scope:
  (command list removed 2026-11-13: superseded by "Human commit list (consolidated)") (req-engineer)
- 2026-11-12 — added test (e) to AC "Git write commands need the human, enforced
  deterministically": a broad allow rule in the git-ignored
  `.claude/settings.local.json` (`Bash(git:*)`, `Bash(git push:*)`) must not
  re-enable `git push`; if it can, the mechanism closes the gap (e.g. a hook).
  Mechanism left open pending the settings-precedence research (human decision,
  2026-11-12) (architect)
- 2026-11-12 — developer: added scope implemented. `.claude/settings.json` (deny/ask rules + third hook `git_policy.py`, `onFailure: block` on all three), new `.claude/hooks/git_policy.py`, new `tests/test_git_policy_hook.py` (34 tests, all offline; no git command executed). Ticked: nothing in the live ACs. Offline-proven only: test (c) compound/indirect-literal forms and (d). Unticked, for the tester after the human commit and in a live session: (a), (b), (e); `git ls-files .claude/commands`; the `.claude/` inventory AC. Known limits are written under the policy AC. Moved to review.
- 2026-11-12 — human command list, superseding the previous list. Run from the repo root:
  (command list removed 2026-11-13: superseded by "Human commit list (consolidated)") (developer)
- 2026-11-12 — reviewer: re-review after bounce 1 plus the added scope, APPROVED (bounce count stays 1 of 2). See the Review section for the probes, known gaps (1)-(3), the over-blocking estimate and the gates. The pending `git config` and threat-model follow-up must land before the tester's live checks (a), (b), (c) and (e). Moved to testing (reviewer)
- 2026-11-12 — developer: reviewer follow-up landed (human decisions). `git config` added to `permissions.ask` and to the hook `ASK`; `PREFIX` extended with `--git-dir|--work-tree|--namespace` (gap 1 closed, stricter only); threat-model paragraph, new AC, known gaps, over-blocking note, open pre-push-hook decision, reworded mod bullet and live-check list (adds (c) and the bare-push deny check) written above; CLAUDE.md section 7 gets the "Working with the git-write policy" bullets. Live tests still for the tester. Ticket stays in testing.
- 2026-11-12 — tester: live and offline verification of the git-write policy. Gates: ruff exit 0, mypy exit 0 (8 files), pytest 174 passed, 2 deselected (40 hook tests). Offline hook probes (stdin JSON): `git config alias.p <push>` ask; `git -C x config --get user.name` ask; `git --work-tree x <push>`, `git --git-dir /tmp/r <push>`, `git --namespace ns <push>` exit 2; `git add -p <push>.md`, `git log --oneline` pass; `git -c alias.p=<push> p` passes (known gap, as documented). Live, this session (settings live): `git push --dry-run /nonexistent HEAD`, bare `git push`, `true && ...`, `true; ...`, `FOO=1 ...` (each the same dry-run to /nonexistent) were all blocked by the hook layer with "PreToolUse:Bash hook error: [python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/git_policy.py"]: Blocked by git policy hook: agents never run git push; the human pushes (CLAUDE.md section 7, Push policy)."; the hook runs first, so the rule layer is not observable on those. Rule layer alone (hook passes the form): `git log --oneline -1 --grep push` denied ("Permission to use Bash with command ... has been denied."), and so were `true && ...`, `true; ...`, `FOO=1 ...` and `cd <repo> && ...` with that same log command; so the deny rules see through `&&`, `;`, VAR= and cd prefixes. Not proven live: the first deny rule (push followed by ` *`) on the bare form with no arguments, because the hook masks it and a bare push with hooks off would hit origin; the hook covers that form. (a) and (c) PASS. (b) and (e) are the human's: steps under "Human live checks". The commit-dependent ACs (`git ls-files`, fresh clone, inventory, origin unchanged) still wait for the human commit. Verdict: PASS pending human live checks (b),(e). Ticket not moved. (tester)
- 2026-11-12 — developer: human decision, `-c`/`--config-env` global option now asks (new `CFG` regex in `git_policy.py`, block still wins; closes the `git -c alias` known gap). Added offline tests (ASKED/PASSED/BLOCKED) with the push word built at runtime, and live-check (e) step 6 (`cat .claude/settings.local.json`). (developer)
- 2026-11-12 — tester: re-test of the `-c`/`--config-env` ask rule. Gates: ruff 0, mypy 0, pytest 186 passed, 2 deselected; with CFG reverted, 8 failed and 43 passed (confirmed). Every listed form asks, passes or blocks as the AC says. Findings F1–F4 are in "Tester re-test". F1: backslash-space, `$'..'`, mid-token quotes, line continuation and `--super-prefix` pass the hook. F2: GIT_CONFIG_* env injection passes. F3: `--config-env k=E <push>` asks instead of blocking. F4: live, the `-c` ask ran with no visible prompt in auto mode. Verdict: added scope GREEN as written; F1–F4 are for the human. Ticket not moved. (tester)
- 2026-11-13 — human decision (approved): F1-F3 are implementation fixes; F4: every former ask becomes a deny (exit 2, "human runs this git command" message) because in auto mode an ask is settled without a human; the ticket-id check moves into the tracked `.githooks/commit-msg` (human flow: orchestrator writes message file, human runs the `-F` commit; `core.hooksPath` enabled per clone by the human). Ticket moved testing -> in-progress. (orchestrator)
- 2026-11-13 — developer: rework done. `git_policy.py`: continuation normalisation, wider `ARG` (note: also allows mid-token quotes, `a"b c"`, which the suggested regex alone does not), `super-prefix|config-env` in `PREFIX` and `CFG`, `ENVCFG` for `GIT_CONFIG_*`, all former asks now exit 2 with the new message. New `.githooks/commit-msg` and `tests/test_commit_msg_hook.py`. README setup step and CLAUDE.md section 7 bullets updated. `.git/hooks`: only `*.sample`. Revert checks in a scratch copy (deleted): without F1 9 tests fail, without F2 3, without F4 26. `permissions.ask` in settings.json left as is (not in scope); live checks and the commit are the human's. For the commit message file: the human adds `.githooks/commit-msg`, `tests/test_commit_msg_hook.py` to the `git add` list. Moved to review. (developer)
- 2026-11-13 — reviewer: CHANGES REQUESTED (bounce 2 of 2). Blocking: the widened `ARG` backtracks exponentially on repeated `$'..'` (n=22 3.7 s, 10k chars >120 s); one-line fix (drop `\$?`) and a timing regression test required; ticket-text fixes (stale ask wording, consolidated human command list). Regex claim verified; F1/F2/F3/F4 and the commit-msg `#` filter each caught by a mutant; ruff 0, mypy 0, hook tests 70 passed; full pytest deferred (load 17-21). Q1-Q3 for the human in the Review section. Moved review -> in-progress (reviewer)
- 2026-11-13 — (human decision, 2026-11-13) (a) `ARG` becomes exactly `(?:\\.|'[^']*'|"[^"]*"|[^\s\\'"])+` (redundant `\$?` dropped); regression test with 22 and 100 `$''` units and a ~10k-char token, each under 1 s. (orchestrator)
- 2026-11-13 — (human decision, 2026-11-13) (b) repeated bare `-C` / `--git-dir` flags backtracked exponentially (pre-existing): apply the reviewer's fix. `PREFIX` bare-flag branch `-(?![Cc]\s|-{SPACE_OPT}\s)\S+`; `CFG` bare-flag branch `-(?!c|C\s|-SPACE_OPT\s|-config-env)\S+`; test with 32 and 300 repeats. (orchestrator)
- 2026-11-13 — (human decision, 2026-11-13) (c) read-only config (`--get`, `--list`) stays denied; no hook change. Workarounds: the Read tool on `.git/config`, or `git rev-parse --git-path hooks` (shows the effective hooks dir and honours `core.hooksPath`). Reviewer Q2 settled. (orchestrator)
- 2026-11-13 — (human decision, 2026-11-13) `.claude/settings.json` is NOT touched in this rework; the decision on its `permissions.ask` rules (reviewer Q1) is still pending. (orchestrator)
- 2026-11-13 — developer, bounce-2 rework: `git_policy.py` has the new `ARG` and both flag-branch fixes (comment added above `PREFIX`). `tests/test_git_policy_hook.py`: new `test_hostile_input_finishes_fast` (6 inputs: 22, 100 and 3334 `$''` units; 32 and 300 `-C`; 300 `--git-dir`; each must finish under 1 s, 10 s hard timeout, exit 0). Fail-on-old-code in scratch copies (deleted): old `ARG` with `\$?` -> 3 failed (77 chars 1.96 s, 311 chars and 10013 chars hit the 10 s timeout); old flag branches -> 3 failed (103 chars 3.29 s, 907 and 3007 chars hit the timeout); fixed code: all under 0.03 s. Ticket text fixed: live-check (b) and the tester list now expect DENY, Known gaps says denied, the scattered command lists replaced by "Human commit list (consolidated)". Gates: ruff 0, mypy 0, `pytest tests/test_git_policy_hook.py tests/test_commit_msg_hook.py` 76 passed (72 policy, 4 commit-msg); full pytest not run (machine kept quiet). Moved in-progress -> review. (developer)
- 2026-11-13 — reviewer: re-review after bounce 2, APPROVED. Decisions (a)-(d) are honoured exactly. Hostile inputs at 10k chars: no exponential path; the worst is quadratic, 0.60 s (`git -C git ...`). Each time-limit test fails on its old pattern (3 + 3 mutants). No over-match in 126 probes; F1-F4 still deny or block. Pyproject list line corrected to a plain add (one hunk; nothing staged). Required before the commit (orchestrator): R1, add the backlog-copy deletion; R2, use the testing/ ticket path. F5 (escaped quotes and quoted option values) and its tested fix are for the human. ruff 0, mypy 0, hook tests 76 passed. Moved review -> testing (reviewer)
- 2026-11-13 — (human decision, 2026-11-13) F5: fix the hook bypass via escaped quotes inside quoted tokens and quoted option values containing a space; apply the reviewer's tested `ARG` and end both bare-flag branches in `{ARG}`. Human-directed change, not a bounce (bounce count stays 2 of 2). (orchestrator)
- 2026-11-13 — (human decision, 2026-11-13) (d): the six `permissions.ask` rules in `.claude/settings.json` become `deny` rules (three patterns per verb, mirroring push); the over-match of `git log --grep config` is an accepted fail-closed cost, recorded under Known gaps. Rationale: settings.json is the only layer when hooks are disabled, an "ask" may not reach a human in auto mode, and agents no longer commit. Human live check added (AC "(d) settings.json denies"). R1 (backlog-copy deletion) and R2 (final ticket path) are applied to the consolidated list, and its settings.json line is no longer conditional. Ticket moved testing -> in-progress (human-directed change, not a bounce). (orchestrator)
- 2026-11-13 — developer, F5 + (d) rework: `git_policy.py` has the reviewer's `ARG` (its last class excludes `$`, so `$` has exactly one parse) and `{ARG}` at the end of both bare-flag branches. `tests/test_git_policy_hook.py`: 3 push forms in BLOCKED, 4 forms in DENIED (3 `-c` forms plus the `-C "a\"b"` commit form), 4 more hostile inputs (`$'\'` x2500 and x40, `"\"` x3334 and x40; all under the 1 s limit). Fail-on-old-code in a scratch copy (deleted): exactly the 7 new policy tests fail, 76 pass; the old commit bypass returned exit 0. `settings.json`: `ask` removed, 21 deny rules, `python3 -m json.tool` OK, hooks block untouched. Gates: ruff 0, mypy 0, `pytest tests/test_git_policy_hook.py tests/test_commit_msg_hook.py` 87 passed in about 1.3 s (83 policy, 4 commit-msg); full suite not run. Live check for (d) is the human's. Moved in-progress -> review. (developer)
- 2026-11-13 — reviewer: re-review of the human-directed F5 + (d) change (not a bounce; the count stays 2 of 2), APPROVED. F5 ARG and `{ARG}` flag branches match the tested form; the pre-F5 hook fails exactly the 7 new tests, and partial mutants fail 5, 2 and 5 (the `$` exclusion is guarded by the hostile inputs). settings.json is valid, deny-only (21 rules), and the hooks block is unchanged. The commit list is complete for the current tree, and its ticket line is updated to testing/ (R2). New pre-existing findings for the human: F6 (medium) unquoted `$(...)` with a space in a `-C` argument passes the hook, e.g. the `rev-parse --show-toplevel` idiom, with a tested fix; F7 (low) a mid-word continuation; F8 (low) quoted subcommand forms, to document. ruff 0, mypy 0, hook tests 87 passed. Moved review -> testing (reviewer)
- 2026-11-13 — (human decision, 2026-11-13) "Bypass fixes are implementation, inside the policy already decided": apply the reviewer's tested F6 and F7 fixes; F8 documented only. Not a bounce (count stays 2 of 2); ticket stays in testing/. (orchestrator)
- 2026-11-13 — developer, F6 + F7: F6 CLOSED, F7 CLOSED, F8 documented under Known gaps (plus the `--attr-source` line). `git_policy.py`: `ARG` gains `$(...)` (one nested paren level), `${...}` and backtick branches, `\$(?![('{])`, and the last class excludes the backtick; the continuation removal is now `re.sub(r"\\\n", "", cmd)`, still the first step after reading the command (nothing before it turns newlines into separators). Tests: 4 substitution forms x (push BLOCKED, commit DENIED, `-c k=v log` DENIED), `pu\<nl>sh`, `com\<nl>mit`, `-C a\<nl>b -c k=v log`, 3 read-only controls in PASSED, 5 hostile ~10k inputs (`$(`, backtick, backslash-newline, `$(a (b`, `${`). Fail-on-old-code in a scratch copy (deleted): exactly the 15 bypass tests fail on the old hook; the controls and hostile inputs pass on old code too (they guard over-match and timing). Gates: ruff 0, mypy 0, hook tests 110 passed (106 policy, 4 commit-msg), slowest hostile 0.04 s. Ticket not moved. (developer)
- 2026-11-13 — reviewer: F6/F7 fix re-check. The code is correct: ARG has one parse per unit, 21 hostile 10k classes take at most 0.04 s (the known quadratic case 1.3 s), and the 15 bypass tests fail on the old hook. R3 (required before the commit, test-only): no test pins the `\$(?![('{])` exclusion (mutant `\$(?!')` passes all 106 while closed `$(a)` runs go 2^n); add the three closed-substitution HOSTILE inputs, which were tested against that mutant. A residual of deep, quoted or escaped substitutions is added to Known gaps (low, deliberate-looking). ruff 0, mypy 0, hook tests 110 passed. Ticket stays in testing/; the human decides on R3. (reviewer)
- 2026-11-13 — developer, R3 (test-only): `HOSTILE` gains `$(a)` x2500, `${a}` x2500 and `$(a)` x40, which pin the `\$(?![('{])` exclusion in ARG. Scratch mutant (`\$(?!')`, deleted): exactly these 3 fail (10011, 10011 and 171 chars; the whole hostile run took 30 s, so the long ones hit the 10 s timeout); the current hook passes all 3 in about 0.03 s each. Hook tests 113 passed (109 policy, 4 commit-msg). `git_policy.py` untouched. Ticket not moved. (developer)
- 2026-11-13 — tester: clean-copy verification (HEAD 8618c7c + the consolidated list's files, untracks and deletion, and the README/CLAUDE/pyproject hunks). PASS on (a)-(f): ruff 0, mypy 0 (8 files), pytest 210 passed, 1 deselected; hook tests 113 passed x3 (3.78-3.87 s), slowest hostile 0.033 s (`"\"` x3334); 70/70 hook probes as expected (push, deny, F5, F6, F7, read-only controls, malformed stdin); settings.json valid, 21 deny rules, no `ask`, hook paths exist; commit list complete with nothing from other tickets; the human `disableAllHooks` check is listed under AC (d). Status testing (ready to close), left in tickets/testing/ for the crew-lead; the human commit and live checks are still open. (tester)
- 2026-11-13 — crew-lead: DoD checked; met except the human-only items (commit via the `-F` flow, `core.hooksPath` per clone, the tester's human live checks and the post-commit ACs), recorded under "Close". The gate hook ran ruff, mypy and pytest on the close move and passed. Moved testing -> done; status done; consolidated list's ticket line updated to `tickets/done/`. `tickets/backlog/INDEX.md` not edited (grooming commit). (crew-lead)
- 2026-11-13 — F6-form live check added to the hooks-disabled check; Known gaps: -c/--config-env/GIT_CONFIG_* hook-only (human decision, 2026-11-13) (req-engineer)
- 2026-11-13 — Known gaps: observed hook-text evasion by crew-lead recorded (human decision, 2026-11-13) (req-engineer)
- 2026-11-14 — req-engineer: restart-based live checks and (c) dropped to Known gaps (lead decision, 2026-11-14); (b)/F4 live evidence recorded from the orchestrator's session
