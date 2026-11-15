---
id: AFL-032
title: Reproduction instructions — README Quickstart and start.sh give the real procedure
requirement: NFR-1 (each result records commit + exact command; reproducible), NFR-4 (documented in README)
paper_ref: Klees §methodology (an evaluation others can repeat); n/a for AFLFast
module: README.md, start.sh
depends_on: [AFL-011, AFL-012, AFL-014]
status: backlog
owner: developer
---

## Goal
The README Quickstart and `start.sh` show an outdated procedure: a plain
`make -C targets`, `run_campaign.py` with no `--kind` or `--freeze-commit`, no
`core.hooksPath`. Replace them with the procedure that actually reproduces the
frozen campaign, so a reader can rebuild the targets and re-run the main campaign
on the frozen commit, then the analysis and plots (lead decision, 2026-11-15).

## Acceptance criteria
- [ ] **Setup.** The README Quickstart's setup block is, in order: create and
      activate the venv, `pip install -r requirements.txt`, `pip install -e .`,
      `git config core.hooksPath .githooks`, `make -C targets clean all` (not a
      plain `make -C targets`: `targets/bin/*` do not depend on the Makefile;
      AFL-011 "Pre-run check: clean rebuild of the targets"). The Homebrew LLVM
      note (ADR-0001) stays.
- [ ] **Reproducing the frozen campaign.** The README gives the exact commands, in
      order: `python harness/run_campaign.py experiments/configs/main.yaml --kind
      main --freeze-commit <hash>` with `<hash>` the frozen commit recorded in
      AFL-011's Log (written out in full once the freeze commit exists), then the
      `harness/aggregate.py` and `harness/plots.py` invocations exactly as AFL-012
      and AFL-014 define them. Each command is checked against the script's
      argument parser on the frozen commit (`run_campaign.py`'s usage lines today:
      `--kind main --freeze-commit H`).
- [ ] **No stale commands.** No command in README.md or `start.sh` (if kept) uses
      `run_campaign.py` without `--kind`, a plain `make -C targets`, or an option
      the scripts do not accept. Test: review against `--help` of each script on
      the frozen commit.
- [ ] **start.sh resolved.** `start.sh` is either deleted or made to run the
      README's procedure, command for command. The ticket's Log records which, and
      why.
- [ ] **Timing.** Lands by stop 7, after the AFL-011 freeze commit is known, so the
      README can name the frozen hash. Off the critical path: it does not gate the
      freeze or the campaign.
- [ ] Docs only: no change under `src/`, `harness/`, `targets/` or
      `experiments/`.

## Technical notes (architect)
`start.sh` (read 2026-11-15) is five lines with no shebang and no `set -e`: venv
creation, `pip install -r requirements.txt`,
`make -C targets`, `run_campaign.py experiments/configs/main.yaml` (no `--kind`, so
the main campaign, with no `--freeze-commit`), then aggregate and plots. It copies
the old Quickstart and nothing references it. Deleting it removes a second copy that
can drift; keeping it means a shebang, `set -e`, and the freeze hash as an
argument. Recommendation: delete. The choice is the developer's (lead decision,
2026-11-15).

## Test approach (tester)
On a clean checkout of the frozen commit, run the setup block as written (no
campaign run needed), then confirm each campaign, aggregate and plot command parses
with `--help` / argument validation. Confirm the hash in the README equals the
freeze hash in AFL-011's Log.

## Log
- 2026-11-15 — created (lead decision, 2026-11-15) (req-engineer)
