---
id: AFL-008
title: CLI
requirement: FR-10
paper_ref: n/a
module: src/fuzzer/cli.py, pyproject.toml ([build-system] + package config), README.md
depends_on: [AFL-007]
status: backlog
owner: developer
---

## Goal
A single-run command-line entry point (FR-10) that exposes target, schedule,
time budget, seed and output directory. SC2 relies on `--schedule
{uniform,fast}` to select the arm.

Open questions (PRD silent; resolve before leaving backlog):
- ~~FR-10 does not list an initial seed-corpus input or a timeout flag. Are these
  needed (see AFL-003 and AFL-004)?~~ Seed corpus **resolved (human, 2026-11-07)**:
  `--seeds DIR` with a default and a hard error, see the ACs below. Timeout flag
  **resolved (human, 2026-11-07)**: `--timeout FLOAT`, default 1.0.
- ~~NFR-1 requires each result to record its commit hash and exact command. Should a
  single CLI run write that record, or only campaign runs (AFL-011)?~~ **Resolved
  (human, 2026-11-07):** every CLI run writes `<out>/run.json`.

## Acceptance criteria
- [ ] `python -m fuzzer.cli --target <bin> --schedule {uniform,fast} --seconds <N>
      --seed <S> --out <dir>` runs one fuzzing session, matching CLAUDE.md §4.
- [ ] `--schedule` accepts only `uniform` and `fast`. Any other value exits
      non-zero with a usage message.
- [ ] `--seed` is passed through as the single source of randomness for the run
      (NFR-1).
- [ ] Output is written under the `--out` directory.
- [ ] `--seconds` sets the run's time budget.
- [ ] `--seeds DIR` passes the initial corpus directory; this is how a target's
      `targets/seeds/<target>/` (containing only `S0`, AFL-011) reaches the run.
      Every file in `DIR` is passed to the fuzzer as an initial seed, which goes
      through `Corpus.observe()` (AFL-004).
- [ ] **Default and hard error (human, 2026-11-07).** When `--seeds` is omitted it
      defaults to `targets/seeds/<basename of --target>/`. cli.py resolves it and
      always sets `FuzzConfig.seeds_dir` (AFL-007, required `Path`). If the resolved
      directory (default or explicit) does not exist or contains no files, the CLI
      exits non-zero with a clear error naming the path, before any execution of the
      target. There is no fallback input of any kind (no `b""`, no generated seed).
      Tests: (a) omitted `--seeds` resolves to `targets/seeds/<basename>/`; (b) missing
      dir: non-zero exit, message names the path, target never executed; (c) empty
      dir: same as (b).
- [ ] **`--max-execs INT` (human, 2026-11-07).** Optional; maps to
      `FuzzConfig.max_execs` (default `None` = no exec cap). Test: `--max-execs 50`
      yields a `FuzzConfig` with `max_execs == 50`; omitted yields `None`.
- [ ] **`--timeout FLOAT` (human, 2026-11-07).** Optional, default `1.0`; maps to
      `FuzzConfig.timeout_s`. Test: omitted yields `1.0`; `--timeout 0.5` yields
      `0.5`.
- [ ] **Provenance `run.json` (NFR-1, human, 2026-11-07).** Every CLI run, before
      fuzzing starts, writes `<out>/run.json` containing at least `argv`, the
      resolved `config`, `commit` (`git rev-parse HEAD`, or `"unknown"` outside a
      repo), `python` version, `platform`, `started_at` and `freeze_commit`
      (the resolved 40-character hash from `--freeze-commit`, or `null` when the
      flag is absent; see the `--freeze-commit` AC). The CLI is the only writer of
      `run.json`. Test: after a short run,
      `run.json` exists, parses as JSON, and contains those keys with `argv` equal
      to the arguments passed.
- [ ] **Dirty-tree flag in `run.json` (human decision, 2026-11-07).** `run.json`
      also contains `"dirty"`, which takes one of three values: `true` iff the
      output of `git status --porcelain --untracked-files=no` is non-empty,
      `false` iff that command succeeds with empty output, and `null` when it
      cannot be determined (e.g. outside a git repo, alongside
      `commit: "unknown"`, or the command fails). `null` never means clean. Only
      modified
      (or staged) tracked files count. Untracked files and directories (e.g.
      `.serena/`) never make the tree dirty; code, targets and configs are tracked,
      and S0 is hash-checked separately (AFL-011). Test (in a temporary git repo or
      with `git` stubbed): a clean tree gives `dirty == false`; an added untracked
      file alone gives `dirty == false`; a modified tracked file gives
      `dirty == true`; a run whose `--out` and working directory are outside any
      git repo (or with `git` stubbed to fail) gives `dirty is None` (JSON `null`)
      and `commit == "unknown"`.
- [ ] **`--freeze-commit HASH` (human decision, 2026-11-07).** Optional. The CLI
      passes the value to the shared helper `resolve_freeze_commit(h: str) -> str`
      in `src/fuzzer/cli.py` (the one helper AFL-011's runner also calls; no other
      copy of this check exists). The helper resolves `h` to its full
      40-character hash with `git rev-parse <h>^{commit}` and then requires
      `git merge-base --is-ancestor <full> HEAD` to exit 0; on either failure it
      raises (e.g. `ValueError`) with a message naming the given hash and HEAD.
      On failure the CLI exits non-zero, before writing anything under `--out` and
      before any target execution. On success `run.json`'s `freeze_commit` is the
      full hash; when the flag is absent it is `null`. Tests (in a temporary git
      repo): (a) flag absent → `freeze_commit is None`; (b) an abbreviated hash of
      an ancestor of HEAD → `freeze_commit` equals the full 40-character hash;
      (c) a non-existent hash → non-zero exit, message names the hash, target never
      executed; (d) a commit not reachable from HEAD (side branch) → same as (c).
- [ ] **Non-empty `--out` is an error (human, 2026-11-07).** If `--out` exists and
      is not empty, the CLI exits non-zero with a message naming the path, before
      writing anything and before any target execution. A missing or empty `--out`
      is accepted. Test: a pre-populated `--out` exits non-zero and its contents are
      unchanged.
- [ ] **Packaging (human, 2026-11-07).** `pyproject.toml` gains a `[build-system]`
      table and package config for `src/fuzzer`, so that after `pip install -e .` in
      the venv, CLAUDE.md §4's `python -m fuzzer.cli ...` command works as written
      from the repo root with no `PYTHONPATH`. README.md documents `pip install -e .`
      in the setup steps. Test: in a fresh venv, `pip install -e .` then
      `python -m fuzzer.cli --help` exits 0.

## Technical notes (architect)
- **Interface:** `main(argv: list[str] | None = None) -> int`, plus
  `if __name__ == "__main__": sys.exit(main())`. It does argparse → `fuzzer.FuzzConfig`
  → `fuzzer.run(cfg)`, plus the provenance work below (`run.json`, and the
  `resolve_freeze_commit(h: str) -> str` helper, which AFL-011's runner imports
  from here so the freeze check exists once).
- **Flags.** Required: `--target PATH --schedule {uniform,fast} --seconds FLOAT --seed
  INT --out DIR`. Optional, confirmed (human, 2026-11-07): `--max-execs INT`,
  `--timeout FLOAT` (default 1.0) and `--freeze-commit HASH` (default absent →
  `null`). Optional, confirmed (human, 2026-11-07):
  `--seeds DIR`, default `targets/seeds/<basename of --target>/`, missing or empty
  dir is a hard error before execution (see AC). cli.py validates this and passes
  the resolved path as `FuzzConfig.seeds_dir`.
- `--schedule` takes its choices from `sorted(schedule.SCHEDULES)`, so the CLI cannot
  drift from schedule.py. argparse exits 2 on any other value, which meets the AC.
- `--seed` maps straight to `FuzzConfig.seed`, the run's only source of randomness.
- **Provenance** (confirmed, human, 2026-11-07): before fuzzing, write
  `<out>/run.json` with `{argv, config, commit, dirty, python, platform, started_at,
  freeze_commit}` (`dirty` true/false/null from `git status --porcelain
  --untracked-files=no`, see AC; `freeze_commit` from `--freeze-commit` via
  `resolve_freeze_commit`, else null; AFL-011 passes it for main-campaign
  trials).
  `commit` comes from `git rev-parse HEAD`, or `"unknown"` outside a repo. Every
  single run then carries NFR-1 provenance, and campaign trials get it for free if
  AFL-011 invokes the CLI once per trial (recommended).
- If `--out` exists and is not empty, exit non-zero, so trials never mix with or
  overwrite earlier results (confirmed, human, 2026-11-07).
- Packaging (confirmed, human, 2026-11-07): `python -m fuzzer.cli` needs `src/` on
  the import path, and `pyproject.toml` has no `[build-system]`/package config. Add
  it and use `pip install -e .`; scope widened to `pyproject.toml` and `README.md`.
  `PYTHONPATH=src` is not the documented route.

## Test approach (tester)
Invoke the CLI with a short budget on toy_parser. Assert the exit code, the output
directory contents, and that an invalid `--schedule` is rejected. `--freeze-commit`
cases (a)-(d) run in a temporary git repo with a side branch.

## Log
- 2026-11-07 — created (req-engineer)
- 2026-11-07 — per human decision: added `--seeds DIR` AC (carries
  `targets/seeds/<target>/`, i.e. S0, into the run); resolved the seed-corpus half
  of the first open question (req-engineer)
- 2026-11-07 — recorded human decision: `--seeds` default `targets/seeds/<basename>/` confirmed; missing/empty dir is a hard pre-execution error, no fallback; tests (a)-(c) added; stale "defaults leave FR-10 unchanged" note removed (req-engineer)
- 2026-11-07 — batch grooming: confirmed `--max-execs`, `--timeout` default 1.0, `run.json` provenance on every CLI run, non-empty `--out` is an error, packaging via `[build-system]` + `pip install -e .` (module += pyproject.toml, README.md); ACs added, open questions resolved (human decision) (req-engineer)
- 2026-11-07 — review fix: `run.json` gains `"dirty": bool` from `git status --porcelain --untracked-files=no` (tracked changes only; untracked dirs like .serena/ ignored), with test (human decision) (req-engineer)
- 2026-11-07 — review fix: `run.json` `dirty` is tri-state true/false/null (null = could not determine, e.g. outside a repo with `commit: "unknown"`; never means clean), test case added; `freeze_commit` added to the run.json keys (null for single CLI runs, set by AFL-011 for campaign trials) (human decision) (req-engineer)
- 2026-11-07 — review fix: added `--freeze-commit HASH` flag; shared helper `resolve_freeze_commit` in src/fuzzer/cli.py resolves via `git rev-parse <h>^{commit}` and requires `git merge-base --is-ancestor <h> HEAD`, non-zero exit on failure, null when absent; AFL-011 runner reuses the helper; CLI stays the single writer of run.json; tests (a)-(d) (human decision) (req-engineer)
