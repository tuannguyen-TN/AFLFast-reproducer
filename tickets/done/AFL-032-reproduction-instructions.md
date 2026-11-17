---
id: AFL-032
title: Reproduction instructions — README Quickstart and start.sh give the real procedure
requirement: NFR-1 (each result records commit + exact command; reproducible), NFR-4 (documented in README)
paper_ref: Klees §methodology (an evaluation others can repeat); n/a for AFLFast
module: README.md, start.sh
depends_on: [AFL-011, AFL-012, AFL-014]
status: done
owner: developer
---

## Goal
The README Quickstart and `start.sh` show an outdated procedure: a plain
`make -C targets`, `run_campaign.py` with no `--kind` or `--freeze-commit`, no
`core.hooksPath`. Replace them with the procedure that actually reproduces the
frozen campaign, so a reader can rebuild the targets and re-run the main campaign
on the frozen commit, then the analysis and plots (lead decision, 2026-11-15).

## Acceptance criteria
- [x] **Setup.** The README Quickstart's setup block is, in order: create and
      activate the venv, `pip install -r requirements.txt`, `pip install -e .`,
      `git config core.hooksPath .githooks`, `make -C targets clean all` (not a
      plain `make -C targets`: `targets/bin/*` do not depend on the Makefile;
      AFL-011 "Pre-run check: clean rebuild of the targets"). The Homebrew LLVM
      note (ADR-0001) stays.
- [x] **Reproducing the frozen campaign.** The README gives the exact commands, in
      order: `python harness/run_campaign.py experiments/configs/main.yaml --kind
      main --freeze-commit <hash>` with `<hash>` the frozen commit recorded in
      AFL-011's Log (written out in full once the freeze commit exists), then the
      `harness/aggregate.py` and `harness/plots.py` invocations exactly as AFL-012
      and AFL-014 define them. Each command is checked against the script's
      argument parser on the frozen commit (`run_campaign.py`'s usage lines today:
      `--kind main --freeze-commit H`).
- [x] **No stale commands.** No command in README.md or `start.sh` (if kept) uses
      `run_campaign.py` without `--kind`, a plain `make -C targets`, or an option
      the scripts do not accept. Test: review against `--help` of each script on
      the frozen commit.
- [x] **start.sh resolved.** `start.sh` is either deleted or made to run the
      README's procedure, command for command. The ticket's Log records which, and
      why.
- [x] **Timing.** Lands by stop 7, after the AFL-011 freeze commit is known, so the
      README can name the frozen hash. Off the critical path: it does not gate the
      freeze or the campaign.
- [x] Docs only: no change under `src/`, `harness/`, `targets/` or
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
- 2026-11-17 — implemented (developer): Setup AC: README Quickstart setup block is venv, `pip install -r requirements.txt`, `pip install -e .`, the core.hooksPath git config, `make -C targets clean all` (with a "not a plain" note); ADR-0001 Homebrew LLVM note kept. Campaign AC: README gives `run_campaign.py experiments/configs/main.yaml --kind main --freeze-commit ff19bef7abb57b1ccbffd0318e2bbcb3c13f9cfc` (the hash in AFL-011's Log entry "2026-11-17 — freeze hash"), then `aggregate.py results/` and `plots.py results/` as run (PROVENANCE.md). Checked: `run_campaign.py --help` lists `--kind` with `main` and `--freeze-commit HASH`; `git diff --quiet ff19bef HEAD -- harness/run_campaign.py src` exits 0; aggregate.py and plots.py take one positional results directory and have no `--help` (plots.py prints an error and its usage line); both gained AFL-033 guards in ee0ac4b, the version the analysis ran with. No stale commands: no `run_campaign.py` without `--kind`, and the only plain `make -C targets` text is the "not a plain" warning. start.sh resolved: deleted with `rm` (architect's recommendation: a second copy of the procedure can drift, and nothing referenced it). Timing: written after the freeze hash was recorded. Docs only: changed README.md, start.sh (deleted) and this ticket. README also notes the ~3 h 20 min runtime, crash reporters off (pointer to AFL-011 Log), the data/SHA256SUMS check, and that a re-run's numbers differ in detail (timeouts are the timing-dependent exception, ADR-0005).
- 2026-11-17 — review: CHANGES REQUESTED (reviewer): all six ACs verified; rejected on two README prose defects: (1) the data check clobbers the reader's `results/` and needs the archive in the cwd; fix: extract into a fresh empty directory, copy `data/SHA256SUMS` and the archive there, run `shasum -a 256 -c SHA256SUMS`; (2) the ADR-0005 sentence conflates the wall-clock budget with the timeout exception; reword. The reviewer ticked the AC boxes with a Bash edit on this file only (orchestrator)
- 2026-11-17 — fixed (developer): (1) README data-check sentence now says to extract the archive into a fresh empty directory, copy `data/SHA256SUMS` and the archive there, and run `shasum -a 256 -c SHA256SUMS`; the same one-sentence correction made in docs/report/PROVENANCE.md (Raw data bullet, nothing else changed there, scope extended for this bounce by the coordinator); (2) README timing sentence reworded to separate the 600 s wall-clock budget from the timeout exception, citing ADR-0005 §4 (checked: §4 is "The timeout exception").
- 2026-11-17 — re-review: APPROVED to testing (reviewer): all six ACs hold. README and PROVENANCE.md data-check sentences now say fresh empty directory, copy data/SHA256SUMS and the archive there, run `shasum -a 256 -c SHA256SUMS`, which works with the top-level results/ layout the coordinator verified. The timing sentence separates the 600 s wall-clock budget from the timeout exception and cites ADR-0005 §4, which is titled "The timeout exception" and limits replay to equal execution counts. The PROVENANCE.md diff changes only that instruction. No home or scratch paths in README.md, PROVENANCE.md or the ticket. Nothing changed under src/, harness/, targets/, experiments/.
- 2026-11-17 — verified (tester): PASS. No campaign process running (pgrep empty). (1) run_campaign.py --help accepts `--kind main` (choice) and `--freeze-commit HASH`, positional config; aggregate.py and plots.py take one positional results dir (main(argv) reads sys.argv[1:], usage `aggregate.py <results_dir>`); targets/Makefile has `all` and `clean` (.PHONY); pyproject.toml has setuptools build-system and packages.find where=src, so `pip install -e .` is valid. (2) data/SHA256SUMS copied to scratch dir: 2841 lines, 2840 start with `results/`, the one other line is the archive `aflfast-results-ff19bef.tar.gz`; `shasum -a 256 -c SHA256SUMS` there reports the archive line as `No such file or directory ... FAILED open or read` (expected, no archive) and the results/ lines as missing until extraction. Nothing copied into the repo. (3) README hash ff19bef7abb57b1ccbffd0318e2bbcb3c13f9cfc (2 occurrences) equals AFL-011 Log `2026-11-17 — freeze hash` (file now in tickets/done/) and `git rev-parse ff19bef`. (4) grep for start.sh outside .venv, results, tickets finds nothing. (5) no /Users/, .claude/jobs/ or /private/tmp/ in the README.md and PROVENANCE.md diffs. Not run: pytest, build, campaign (per brief).
- 2026-11-17 — DoD verified, moved to done (crew-lead): all six ACs ticked with Log evidence (reviewer approved on second pass, tester PASS), and the change is docs only (README.md, PROVENANCE.md, start.sh deleted; nothing under src/, harness/, targets/, experiments/).
