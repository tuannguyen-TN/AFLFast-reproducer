---
id: AFL-008
title: CLI
requirement: FR-10
paper_ref: n/a
module: src/fuzzer/cli.py
depends_on: [AFL-007]
status: backlog
owner: developer
---

## Goal
A single-run command-line entry point (FR-10) that exposes target, schedule,
time budget, seed and output directory. SC2 relies on `--schedule
{uniform,fast}` to select the arm.

Open questions (PRD silent; resolve before leaving backlog):
- FR-10 does not list an initial seed-corpus input or a timeout flag. Are these
  needed (see AFL-003 and AFL-004)?
- NFR-1 requires each result to record its commit hash and exact command. Should a
  single CLI run write that record, or only campaign runs (AFL-011)?

## Acceptance criteria
- [ ] `python -m fuzzer.cli --target <bin> --schedule {uniform,fast} --seconds <N>
      --seed <S> --out <dir>` runs one fuzzing session, matching CLAUDE.md §4.
- [ ] `--schedule` accepts only `uniform` and `fast`. Any other value exits
      non-zero with a usage message.
- [ ] `--seed` is passed through as the single source of randomness for the run
      (NFR-1).
- [ ] Output is written under the `--out` directory.
- [ ] `--seconds` sets the run's time budget.

## Technical notes (architect)
- **Interface:** `main(argv: list[str] | None = None) -> int`, plus
  `if __name__ == "__main__": sys.exit(main())`. It does argparse → `fuzzer.FuzzConfig`
  → `fuzzer.run(cfg)` and contains no other logic.
- **Flags.** Required: `--target PATH --schedule {uniform,fast} --seconds FLOAT --seed
  INT --out DIR`. Optional (proposed default — confirm): `--max-execs INT`,
  `--timeout FLOAT` (default 1.0) and `--seeds DIR`. These expose the AFL-003/004/007
  knobs; their defaults leave the FR-10 surface unchanged.
- `--schedule` takes its choices from `sorted(schedule.SCHEDULES)`, so the CLI cannot
  drift from schedule.py. argparse exits 2 on any other value, which meets the AC.
- `--seed` maps straight to `FuzzConfig.seed`, the run's only source of randomness.
- **Provenance** (proposed default — confirm): before fuzzing, write
  `<out>/run.json` with `{argv, config, commit, python, platform, started_at}`.
  `commit` comes from `git rev-parse HEAD`, or `"unknown"` outside a repo. Every
  single run then carries NFR-1 provenance, and campaign trials get it for free if
  AFL-011 invokes the CLI once per trial (recommended).
- If `--out` exists and is not empty, exit non-zero, so trials never mix with or
  overwrite earlier results (proposed default — confirm).
- Packaging: `python -m fuzzer.cli` needs `src/` on the import path, and
  `pyproject.toml` has no `[build-system]`/package config. Either add that and
  `pip install -e .`, or document `PYTHONPATH=src`. Whichever you choose, the
  `pyproject.toml`/README edit needs the ticket scope widened (req-engineer).

## Test approach (tester)
Invoke the CLI with a short budget on toy_parser. Assert the exit code, the output
directory contents, and that an invalid `--schedule` is rejected.

## Log
- 2026-11-07 — created (req-engineer)
