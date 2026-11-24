# AFLFast Reproducer

Tuan · Computer Security, Syracuse University · Fall 2026

A small AFL-style greybox fuzzer built to test one claim from AFLFast (Böhme et al., CCS 2016): that its FAST power schedule beats a uniform schedule. The two schedules differ only in how many mutants each input gets. The evaluation follows Klees et al. (CCS 2018): repeated trials, planted bugs and statistical tests.

**Result:** no detectable difference. None of the six pre-registered measures differed at Holm-adjusted p < 0.05 (all adjusted p = 1). Full numbers: [summary](https://github.com/tuannguyen-TN/AFLFast-reproducer/blob/v1.3-submission/docs/report/summary.md).

## Requirements

- macOS on Apple silicon (the only platform tested)
- Python 3.10 or newer as `python3` (tested with 3.12; macOS's own `/usr/bin/python3` is 3.9, which is too old)
  - Check with `python3 --version`. If it's below 3.10, run `brew install python@3.12` and use `python3.12` in the first Setup command.
- Homebrew LLVM: `brew install llvm`
  - Apple's own clang hangs under AddressSanitizer on macOS 26.
  - The Makefile uses `/opt/homebrew/opt/llvm/bin/clang` if it exists, and otherwise falls back without warning to `clang` on your PATH (Apple's clang on a stock Mac).

## Setup

The zip unzips to `AFLFast-reproducer/`; run everything from inside it:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
make -C targets clean all
pytest
```

- `make` builds the targets into `targets/bin/`. The clang lines it prints should start with `/opt/homebrew/opt/llvm/`; if they don't, Homebrew LLVM isn't being used.
- `pytest` runs the fast tests: expect `607 passed, 10 deselected` in about 3 minutes. `pytest -m slow` runs the rest.
- Keep the virtual environment active for everything below.

## Demo: fuzz for 3 minutes with each schedule

```bash
python -m fuzzer.cli --target targets/bin/toy_parser --schedule uniform --seconds 180 --seed 7000 --timeout 5 --out results/demo/uniform
python -m fuzzer.cli --target targets/bin/toy_parser --schedule fast --seconds 180 --seed 7000 --timeout 5 --out results/demo/fast
for s in uniform fast; do (head -n 1 results/demo/$s/metrics.csv; tail -n 1 results/demo/$s/metrics.csv) | column -s, -t; done
```

- Each run prints nothing and stops after 3 minutes (about 6 minutes for both), which is long enough to reach the first crash even at 5 executions per second.
- The last command prints each run's final row under its column names: `execs` (inputs run), `edges` (edges covered), `corpus_size` (inputs kept in `queue/`), `crash_events` (crashing inputs) and `crashes_saved` (the distinct crashes in `crashes/`).
- `crashes/` saves a crash only when it reaches a new path or crash site, so `crashes_saved` can be lower than `crash_events`. Each saved crash is the input (`.bin`) plus a JSON file with the AddressSanitizer report in its `stderr` field. `queue/` holds the inputs the fuzzer kept.
- Should match: every crash is toy_parser's easy bug, a heap over-read in `scan()`, and edges end at 8–9 for UNIFORM and 7–8 for FAST. Varies with machine load: executions (we measured 7 to 21 per second). One short run says nothing about which schedule is better.

## Reproduce the report's results

You need a git clone (the campaign checks the commit history), about 3 h 20 min, and the macOS crash reporters turned off.

1. Clone the submission, then do the Setup steps inside it:
   ```bash
   git clone https://github.com/tuannguyen-TN/AFLFast-reproducer
   cd AFLFast-reproducer && git checkout v1.3-submission
   ```
2. Turn off the crash reporters. They analyse every crash, which slows the trials and could penalise the schedule that crashes more.
   ```bash
   launchctl disable gui/$(id -u)/com.apple.ReportCrash
   launchctl bootout gui/$(id -u)/com.apple.ReportCrash
   sudo launchctl disable system/com.apple.ReportCrash.Root
   sudo launchctl bootout system/com.apple.ReportCrash.Root
   ```
3. Run the main campaign (3 programs × 2 schedules × 10 trials of 10 minutes, three at a time), then the analysis:
   ```bash
   python harness/run_campaign.py experiments/configs/main.yaml --kind main --freeze-commit ff19bef7abb57b1ccbffd0318e2bbcb3c13f9cfc
   python harness/aggregate.py results/
   python harness/plots.py results/
   ```
4. Compare `results/summary.md` and `results/figures/` with the committed versions in `docs/report/`. The numbers won't match exactly: each trial stops on wall-clock time, so it runs a different number of inputs.
5. Turn the crash reporters back on:
   ```bash
   launchctl enable gui/$(id -u)/com.apple.ReportCrash
   launchctl bootstrap gui/$(id -u) /System/Library/LaunchAgents/com.apple.ReportCrash.plist
   sudo launchctl enable system/com.apple.ReportCrash.Root
   sudo launchctl bootstrap system /System/Library/LaunchDaemons/com.apple.ReportCrash.Root.plist
   ```

**Re-run only the analysis.** The raw data from the main run is available from me on request. Copy its `results/` folder into a clone that has no `results/main/` yet (not one where you ran step 3), run the two analysis commands from step 3, then:

```bash
cmp results/summary.csv docs/report/summary.csv && echo "summary.csv identical"
```

## What's in the repository

- `src/fuzzer/`: the fuzzer (input selection, power schedules, mutation, execution, coverage)
- `targets/`: three fuzz targets in C with two planted bugs each, plus the coverage runtime (`cov_rt.c`) and a small spike program; `ground_truth.json` lists each bug and the function it crashes in
- `harness/`: the campaign runner, crash de-duplication, aggregation and plots
- `experiments/configs/`: the frozen campaign settings
- `tests/`: the test suite
- `docs/`: requirements, design records and the committed results (not in the submission zip, except ADR-0003, which a test reads)
- `.claude/`, `CLAUDE.md`, `.githooks/`, `tickets/`: the AI-agent setup and work records used during development; the fuzzer and the campaign don't need them (two test files check the hooks in `.githooks/` and `.claude/hooks/`)

## How it was built

AI coding agents (Claude Code) wrote nearly all of the code, working in roles I defined; a small part came in with the first commit. From 14 November, an AI assistant (Claude) made day-to-day lead decisions. I approved every commit and push.

## References

- M. Böhme, V.-T. Pham, A. Roychoudhury. *Coverage-based Greybox Fuzzing as Markov Chain.* ACM CCS 2016. doi:10.1145/2976749.2978428
- G. Klees, A. Ruef, B. Cooper, S. Wei, M. Hicks. *Evaluating Fuzz Testing.* ACM CCS 2018. doi:10.1145/3243734.3243804

The fuzzer runs only against the bundled targets, on your own machine.
