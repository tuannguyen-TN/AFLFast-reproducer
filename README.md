# AFLFast Reproducer

A naive coverage-guided greybox fuzzer (AFL-style) that **reproduces AFLFast's
power-schedule advantage** under the **evaluation methodology of Klees et al.**

- **What it reproduces:** AFLFast (CCS 2016) — energy spent on rare-path seeds
  beats uniform energy allocation.
- **How it measures it:** _Evaluating Fuzz Testing_ (CCS 2018) — repeated trials,
  Mann-Whitney U significance, A12 effect size, honest crash de-duplication.

See **`docs/PRD.md`** for full requirements and **`CLAUDE.md`** for the repo map,
commands, and working agreement. The development process (roles, tickets, SDLC)
lives in **`.claude/agents/`** and **`tickets/`**.

## Quickstart

Reproduce the frozen main campaign, then the analysis. Run everything from the repository root.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .   # makes `python -m fuzzer.cli` work from the repo root
git config core.hooksPath .githooks   # tracked commit-msg hook (ticket-id check); local git config, does not travel with a clone
make -C targets clean all   # not a plain `make -C targets`: targets/bin/* do not depend on the Makefile (AFL-011)
```

> Requires macOS with Homebrew LLVM (`brew install llvm`): Apple clang's ASan hangs on macOS 26.x. See ADR-0001.

Then, on a clean tree whose HEAD descends from the freeze commit
`ff19bef7abb57b1ccbffd0318e2bbcb3c13f9cfc` (recorded in AFL-011's Log, entry "2026-11-17 — freeze hash"):

```bash
python harness/run_campaign.py experiments/configs/main.yaml --kind main \
    --freeze-commit ff19bef7abb57b1ccbffd0318e2bbcb3c13f9cfc
python harness/aggregate.py results/
python harness/plots.py results/
```

The campaign (3 targets x 2 schedules x 10 trials, 600 s each, concurrency 3) took about 3 h 20 min on
the machine used. It ran with the macOS crash reporters turned off; see AFL-011's Log in `tickets/` for
how. `aggregate.py` and `plots.py` gained input guards after the freeze (AFL-033, commit `ee0ac4b`); the
published analysis ran with that version. It is in `docs/report/`; `docs/report/PROVENANCE.md` has
hashes and times. The raw-data archive is kept off the repository. To check it, extract the archive into a fresh empty
directory, copy `data/SHA256SUMS` and the archive into that directory, and run
`shasum -a 256 -c SHA256SUMS` there. Without the archive you can still re-run the campaign.

**Crash reporters.** The main campaign ran with both macOS crash reporters off: the per-user agent
`com.apple.ReportCrash` and the system daemon `com.apple.ReportCrash.Root`. They cost CPU on every
crash (the PRD records that this "slows the trials and so would bias the item (d) comparison"), and
they could penalise the arm that crashes more. AFL's `afl-fuzz` (`check_crash_handling()` on
macOS, kept in AFLFast) refuses to run while the per-user `com.apple.ReportCrash` agent is loaded,
unless `AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES` is set, since the reporter's delay can make
crashes look like timeouts; AFL++'s `docs/INSTALL.md` says the crash
reporting daemon must be turned off for fuzzing. A re-run with them on may differ.

Turn them off (the per-user agent needs no sudo; the system daemon needs sudo):

```bash
launchctl disable gui/$(id -u)/com.apple.ReportCrash
launchctl bootout gui/$(id -u)/com.apple.ReportCrash
sudo launchctl disable system/com.apple.ReportCrash.Root
sudo launchctl bootout system/com.apple.ReportCrash.Root
```

Turn them back on:

```bash
launchctl enable gui/$(id -u)/com.apple.ReportCrash
launchctl bootstrap gui/$(id -u) /System/Library/LaunchAgents/com.apple.ReportCrash.plist
sudo launchctl enable system/com.apple.ReportCrash.Root
sudo launchctl bootstrap system /System/Library/LaunchDaemons/com.apple.ReportCrash.Root.plist
```

A re-run's numbers will differ in detail: each trial stops on a 600 s wall-clock budget, so execution counts vary. Given the same execution count, replay is exact except where a timeout changes an outcome (ADR-0005 §4).

## Papers (download locally into `docs/papers/`)

- `aflfast-ccs2016-coverage-based-greybox-fuzzing-as-markov-chain.pdf`
- `klees-ccs2018-evaluating-fuzz-testing.pdf`

## Scope & ethics

Fuzzing runs only against the in-repo targets we own, entirely locally. This is a
methodology reproduction, not an offensive-security tool.
