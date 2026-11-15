---
id: AFL-008
title: CLI
requirement: FR-10
paper_ref: n/a
module: src/fuzzer/cli.py, pyproject.toml ([build-system] + package config), README.md
depends_on: [AFL-007]
status: done
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
- [x] `python -m fuzzer.cli --target <bin> --schedule {uniform,fast} --seconds <N>
      --seed <S> --out <dir>` runs one fuzzing session, matching CLAUDE.md §4.
- [x] `--schedule` accepts only `uniform` and `fast`. Any other value exits
      non-zero with a usage message.
- [x] `--seed` is passed through as the single source of randomness for the run
      (NFR-1).
- [x] Output is written under the `--out` directory.
- [x] `--seconds` sets the run's time budget.
- [x] `--seeds DIR` passes the initial corpus directory; this is how a target's
      `targets/seeds/<target>/` (containing only `S0`, AFL-011) reaches the run.
      The seed files of `DIR` are passed to the fuzzer as initial seeds, each of
      which goes through `Corpus.observe()` (AFL-004).
- [x] **Seed files: non-hidden, sorted (human decision, 2026-11-12; ADR-0005 §1).**
      Only regular files in `DIR` whose names do not start with `.` are loaded, in
      `sorted()` filename order (Python sorts `str` by code point, so the order does
      not depend on the locale). Only regular files are seeds: a subdirectory or
      any other entry that is not a file is never loaded (human decision,
      2026-11-12); AFL-007's `seed_files` filters on `p.is_file()`. The CLI uses AFL-007's seed-file function in
      `fuzzer.py` (the one `run()` loads from) and has no copy of the rule. Reason:
      Finder writes `.DS_Store` into any directory it opens; it is untracked
      (gitignored once AFL-015 lands), so the dirty-tree check never sees it, and
      it would otherwise become a second initial seed. `run.json` gains a key
      `seed_files`: the list, in load order, of the seed files loaded, each as
      `{"name": <file name>, "sha256": <64-char lowercase hex>}`. Tests: (a) a seeds
      dir holding `S0` and `.DS_Store` loads only `S0`, and `run.json`'s
      `seed_files` is exactly `[{"name": "S0", "sha256": <SHA-256 of S0>}]`;
      (b) a dir holding `b` and `a` loads `a` then `b`, and `seed_files` lists
      `a` then `b`; (c) a seeds dir holding `S0` and a subdirectory `sub/` loads
      only `S0`, and `run.json`'s `seed_files` lists only `S0`.
- [x] **Default and hard error (human, 2026-11-07).** When `--seeds` is omitted it
      defaults to `targets/seeds/<basename of --target>/`. cli.py resolves it and
      always sets `FuzzConfig.seeds_dir` (AFL-007, required `Path`). If the resolved
      directory (default or explicit) does not exist or contains no seed file
      (per AC "Seed files: non-hidden, sorted"; a dir holding only `.DS_Store`,
      or only a subdirectory, counts as empty), the CLI
      exits non-zero with a clear error naming the path, before any execution of the
      target. There is no fallback input of any kind (no `b""`, no generated seed).
      Tests: (a) omitted `--seeds` resolves to `targets/seeds/<basename>/`; (b) missing
      dir: non-zero exit, message names the path, target never executed; (c) empty
      dir: same as (b); (d) a dir holding only `.DS_Store`: same as (b); (e) a dir
      holding only a subdirectory counts as empty: same as (b).
- [x] **`--max-execs INT` (human, 2026-11-07).** Optional; maps to
      `FuzzConfig.max_execs` (default `None` = no exec cap). Test: `--max-execs 50`
      yields a `FuzzConfig` with `max_execs == 50`; omitted yields `None`.
- [x] **`--timeout FLOAT` (human, 2026-11-07).** Optional, default `1.0`; maps to
      `FuzzConfig.timeout_s`. Test: omitted yields `1.0`; `--timeout 0.5` yields
      `0.5`.
- [x] **Provenance `run.json` (NFR-1, human, 2026-11-07).** Every CLI run, before
      fuzzing starts, writes `<out>/run.json` containing at least `argv`, the
      resolved `config`, `commit` (`git rev-parse HEAD`, or `"unknown"` outside a
      repo), `python` version, `platform`, `started_at`, `seed_files` (see AC
      "Seed files: non-hidden, sorted") and `freeze_commit`
      (the resolved 40-character hash from `--freeze-commit`, or `null` when the
      flag is absent; see the `--freeze-commit` AC). `started_at` is a wall-clock
      timestamp for provenance only; no duration is measured from it (AFL-007 AC
      "Clock", human decision, 2026-11-12). The CLI is the only writer of
      `run.json`. Test: after a short run,
      `run.json` exists, parses as JSON, and contains those keys with `argv` equal
      to the arguments passed.
- [x] **Dirty-tree flag in `run.json` (human decision, 2026-11-07).** `run.json`
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
- [x] **`--freeze-commit HASH` (human decision, 2026-11-07).** Optional. The CLI
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
- [x] **Invalid run parameters surface cleanly (human decision, 2026-11-12;
      AFL-007 AC "Parameter validation").** When `--max-execs` < 1, `--seconds`
      <= 0 or `--timeout` <= 0, the CLI exits non-zero with the `ValueError`
      message from AFL-007's validation (which names the parameter) on stderr and
      no Python traceback, before writing anything under `--out` and before any
      target execution. The CLI reuses AFL-007's validation and has no copy of its
      own. Tests: `--max-execs 0`, `--seconds 0` and `--timeout 0` each exit
      non-zero, stderr names that parameter and contains no `Traceback`, the
      target is never executed, and `--out` is absent or empty afterwards.
- [x] **Non-empty `--out` is an error (human, 2026-11-07).** If `--out` exists and
      is not empty, the CLI exits non-zero with a message naming the path, before
      writing anything and before any target execution. A missing or empty `--out`
      is accepted. Test: a pre-populated `--out` exits non-zero and its contents are
      unchanged.
- [x] **Packaging (human, 2026-11-07).** `pyproject.toml` gains a `[build-system]`
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
  seed_files, freeze_commit}` (`dirty` true/false/null from `git status --porcelain
  --untracked-files=no`, see AC; `freeze_commit` from `--freeze-commit` via
  `resolve_freeze_commit`, else null; AFL-011 passes it for main-campaign
  trials).
  `commit` comes from `git rev-parse HEAD`, or `"unknown"` outside a repo. Every
  single run then carries NFR-1 provenance, and campaign trials get it for free if
  AFL-011 invokes the CLI once per trial (recommended).
- Because `run.json` is written before `fuzzer.run(cfg)` starts, the "Invalid run
  parameters" AC needs AFL-007's validation callable on its own (e.g. a function
  in `fuzzer.py` that `run()` calls first and the CLI calls before writing
  `run.json`); the exact shape is the architect's call (req-engineer note,
  2026-11-12).
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

## Review (reviewer, 2026-11-14)

**Verdict: changes requested -> in-progress.** One AC is not met (`--freeze-commit`), and the
defect fails open on a pre-registration control. Everything else checks out (evidence below).

Gates (AFL-008 scope): `pytest tests/test_cli.py` 22 passed; `mypy src` clean;
`ruff check src tests/test_cli.py` clean; `python -m fuzzer.cli --help` from `/tmp`, with
`PYTHONPATH` empty, exits 0 and imports `fuzzer` from `src/` (editable install in `.venv`).
I did not run whole-repo `ruff check .` or the full pytest. Per the brief, they currently fail on
other tickets' in-flight files (test_dedup.py, test_tlv_parser.py, the test_toy_parser
ground-truth check), and that does not count against AFL-008.

### Required changes
1. **Empty `--freeze-commit` fails open (AC `--freeze-commit`).** At `src/fuzzer/cli.py:81`,
   `if a.freeze_commit` treats `--freeze-commit ""` as if the flag were absent. I reproduced
   it: exit 0, `run.json` `freeze_commit: null`, and the helper is never called. The AC says
   `null` only "when the flag is absent", and says the CLI passes the value to
   `resolve_freeze_commit`. If AFL-011 ever passes an empty value from config, a trial runs as
   "no freeze" without any error. Fix: test `a.freeze_commit is not None`, so `""` reaches
   the helper, `git rev-parse "^{commit}"` fails, and the CLI exits 2. Add a test case
   `--freeze-commit ""` that checks a non-zero exit, that the target never ran, and that
   `--out` is absent or empty (parametrize it into `test_freeze_commit_rejected`).
2. **The resolve-failure message is inaccurate (AC `--freeze-commit`: "message naming the
   given hash and HEAD").** At `src/fuzzer/cli.py:37` the message says `(HEAD checked)`, but
   on this path HEAD was never consulted. The text satisfies the AC's wording without being
   true. Name HEAD truthfully, e.g. "... does not resolve to a commit (HEAD is <sha>)", using
   `rev-parse HEAD` when it is available and "unknown" otherwise. The ancestor-failure
   message at :41 is fine.

### Per-AC findings
- Command shape (CLAUDE.md s4): met. All five flags are required (`cli.py:56-60`), and
  `test_run_writes_provenance` does a full stubbed run that writes `metrics.csv`.
- `--schedule` only uniform|fast: met. Choices come from `sorted(SCHEDULES)` (`cli.py:57`),
  and argparse exits 2 with usage. `test_bad_schedule_exits_nonzero` checks exit 2 and that
  the target never ran.
- `--seed` is the only randomness: met. It maps straight to `FuzzConfig.seed`
  (`test_config_mapping`). The CLI has no RNG and nothing seeds from the clock or PID.
- Output under `--out`: met (`run.json` and `metrics.csv` under `--out`).
- `--seconds` budget: met (`test_config_mapping` gives `seconds == 100.0`).
- `--seeds DIR`: met. It sets `FuzzConfig.seeds_dir` (`cli.py:71-72`), and `run()` loads
  through `Corpus.observe()` (AFL-007).
- Seed files non-hidden/sorted: met. `cli.py:76` calls `fuzzer.seed_files` and has no copy of
  it. `test_seed_files_dsstore_and_subdir` covers (a)+(c) together with an exact `seed_files`
  equality, and `test_seed_files_sorted` covers (b). The `sha256` values are `hexdigest()`
  (64-char lowercase). Because `run()` uses the same function, "loads only S0" follows.
- Default + hard error: met. The default is `Path("targets/seeds")/basename`, relative to
  the cwd (`cli.py:71`). The AC and the Packaging AC both assume a run from the repo root,
  and a wrong cwd hits the hard error, which names the path. No fallback input exists.
  `test_default_seeds_dir` covers (a), and `test_bad_seeds_dir[missing|empty|ds_store|subdir]`
  covers (b)-(e): the message names the path, there is no traceback, the target never runs,
  and `--out` is absent or empty.
- `--max-execs`: met (50 -> 50 is checked as 5 -> 5; omitted -> None).
- `--timeout`: met (omitted -> 1.0; 0.5 -> 0.5).
- `run.json` provenance: met. The key set `{argv, config, commit, dirty, python, platform,
  started_at, seed_files, freeze_commit}` (`cli.py:87-98`) matches the AC, the technical
  notes and ADR-0005 s1/s2. `started_at` is UTC wall-clock, provenance only, and nothing is
  measured from it. `run.json` sits outside the ADR-0005 s3 replay scope. The file is written
  before `fuzzer.run`, and the CLI is its only writer. The test checks the keys and that
  `argv` equals the arguments passed.
- `dirty` tri-state: met. `git status --porcelain --untracked-files=no` (`cli.py:49-50`)
  gives True when output is non-empty, False when empty, and None when the command fails
  or git cannot run. `test_dirty_states` covers clean -> False, untracked file alone ->
  False, and modified tracked file -> True. `test_outside_repo_dirty_null` (via
  GIT_CEILING_DIRECTORIES) and `test_git_missing_dirty_null` (PATH="") give None and
  "unknown".
- `--freeze-commit`: **not met** (required changes 1-2). The helper itself is correct:
  `rev-parse <h>^{commit}` resolves the full hash, and `merge-base --is-ancestor <full> HEAD`
  (`cli.py:35-42`) rejects anything else. A multi-rev input such as `A..B` makes rev-parse
  print two lines, and the ancestor check then rejects it. Tests (a)-(d) are present and
  meaningful (`test_freeze_commit_ancestor_abbreviated`, `test_freeze_commit_rejected`
  [missing|side], plus the `freeze_commit is None` check in `test_run_writes_provenance`).
- Invalid run parameters: met. `fuzzer.validate_config` is reused (`cli.py:75`) with no copy.
  `test_invalid_params` checks the stderr name, that there is no traceback, that the target
  never ran, and that `--out` is absent or empty.
- Non-empty `--out`: met (`cli.py:79-80`; a file at `--out` is also rejected). The test checks
  that the contents are unchanged and that the message names the path. `test_empty_out_accepted`
  covers the empty case.
- Packaging: met on the evidence. The `[build-system]` (setuptools>=61) and
  `[tool.setuptools.packages.find] where=["src"]` hunks are the only AFL-008 hunks in
  pyproject.toml. The ruff `extend-exclude` hunk is AFL-015's. README adds `pip install -e .`
  after `pip install -r requirements.txt`. The AC's "fresh venv" test is best read as a fresh
  venv that follows the README. `[project]` declares no dependencies, so a bare
  `pip install -e .` cannot import `coverage.py`'s numpy. Declaring dependencies is outside
  this ticket; requirements.txt is the project's dependency route. The `.venv` editable
  install, shown by `pip show` (editable location = repo) and by `--help` from `/tmp` with no
  PYTHONPATH, proves the packaging mechanism. Tester: if installs are permitted at your
  stage, run the end-to-end check (new venv, `pip install -r requirements.txt`,
  `pip install -e .`, `--help` exits 0 from the repo root).
  Note: `test_module_help` sets `PYTHONPATH=src`, so it tests the `__main__` guard, not the
  packaging.

### Invariants
- NFR-2 variable isolation: intact. The CLI reads `SCHEDULES` only for argparse choices,
  passes `schedule` through unchanged, and has no arm-dependent branch.
- Blind mutation: unaffected (mutator.py is not touched).
- `fuzzer.py` is untouched by AFL-008. Its mtime is 2026-11-12 (AFL-007); cli.py and
  test_cli.py are dated 2026-11-14.
- Every error path in the CLI (argparse, ValueError) exits 2 with a message, without a
  traceback, before any write under `--out` or any target execution.

### test_cli.py changed on disk after the developer's last write
I reviewed the file as it is now. All 22 tests trace to AFL-008 ACs, and I found no content
from outside the ticket: no other modules are patched and no unrelated fixtures or tests are
present. I cannot tell what changed without the earlier version. A linter or formatter pass
(mtime 21:47:25, about a minute after cli.py) is the likely cause.

### Non-blocking notes (for AFL-011 / later)
- `commit`, `dirty` and the freeze check all run git in the **cwd**, not in the fuzzer's own
  repo. If AFL-011 invokes the CLI from inside another repo, those values would come from that
  repo. AFL-011 must invoke the CLI with cwd = repo root (it also needs that for the default
  `--seeds`).
- `.gitignore` now has `*.egg-info/`, which covers the untracked
  `src/greybox_fuzz_repro.egg-info/`.
- A missing or uninstrumented `--target` fails inside `fuzzer.run` after `run.json` is
  written. The result is a traceback and a non-empty `--out`, so a re-run is refused until
  `--out` is cleared. No AC covers this. A target-existence pre-check could come in a later
  ticket if wanted.

### Re-review (reviewer, 2026-11-14, bounce-1 fixes)

**Verdict: approve -> testing. Nothing blocking.** I re-reviewed only the changes.

Gates (AFL-008 scope): `pytest tests/test_cli.py` 25 passed; `mypy src` clean;
`ruff check src tests/test_cli.py` clean; `python -m fuzzer.cli --help` from `/tmp` exits 0.
`fuzzer.py` is still untouched (mtime 2026-11-12).

1. **Required change 1, empty `--freeze-commit`: resolved.** `cli.py:86` now tests
   `a.freeze_commit is not None`, so `""` reaches `resolve_freeze_commit`, `git rev-parse
   "^{commit}"` fails, and the CLI exits 2. `test_freeze_commit_rejected[empty]`
   (`tests/test_cli.py:253-265`) asserts a non-zero exit, that the target never ran, that
   there is no traceback, and that `--out` is absent or empty. It would fail under the old
   truthiness test, which exited 0. The `freeze_commit` box is ticked again.
2. **Required change 2, message: resolved.** The resolve failure now reports the real HEAD
   (`cli.py:37-40`): `freeze commit '' does not resolve to a commit (HEAD is unknown)` outside
   a repo, and HEAD's full hash inside one.
3. **New target pre-check (lead decision, 2026-11-14): sound.** `cli.py:79-80` rejects a
   `--target` that is not a regular file or not executable (`is_file()` and `os.X_OK`). It
   raises the ValueError inside the existing try block, so the CLI exits 2, names the path,
   prints no traceback, and runs this check before anything is written or executed. This
   removes the first-pass note about a traceback and a non-empty `--out`. The check runs in
   the CLI only, so `run()` and both arms are unchanged (NFR-2 intact).
   `test_bad_target[missing|not_exec]` asserts a non-zero exit, that the path is named, that
   the target never ran, and that `--out` is empty.

**The fixture change did not weaken any existing assertion.** The autouse `target` fixture
(`tests/test_cli.py:43-48`) creates `tmp_path/tgt` (an executable `#!/bin/sh` stub) at the
path `args()` already used. No assertion was removed or loosened:
- Before this change, `tgt` never existed and the stubbed Executor never looked at it. Now
  it exists so that runs which should succeed get past the new check.
- The seeds, params, out and freeze error tests all still reach their own check, and each
  still asserts on its own needle (the seeds dir, the parameter name, the out path, or the
  hash). None of them can pass because of the target error: that message names `tgt`, not
  their needle.
- `test_config_mapping`'s literal `"t"` became `str(tmp_path / "tgt")`. Its assertions are
  unchanged.
- `test_default_seeds_dir` still derives `targets/seeds/tgt` from the basename.
- The `tgt` stub sits outside the temporary git repo (`tmp_path/repo`), so `dirty` is not
  affected.

**Non-blocking**
- The new target pre-check is a lead decision recorded only in the Log. No AC states it.
  Crew lead or req-engineer may want to add a one-line AC so that testing and the AFL-011
  pre-flight can cite it.
- In the `[empty]` case the needle is `""`, which trivially matches any stderr. That is
  harmless, because the other assertions carry the test. An optional
  `assert "''" in err` would pin the message.
- No test asserts that the resolve-failure message contains HEAD's hash. I verified the
  message manually.
- Carried over for the tester: the fresh-venv check (`pip install -r requirements.txt`, then
  `pip install -e .`, then `--help` exits 0), if installs are allowed at the testing stage.

## Test (tester, 2026-11-14)

**Verdict: PASS, ready to close.** Every AC was verified with the real CLI against the built
`targets/bin/tlv_parser` (not rebuilt) and with the unit tests. No defects were found.
All outputs went to `$CLAUDE_JOB_DIR/tmp/afl008-e2e/`; nothing was written under `results/` or in
the repo.

Gates (AFL-008 scope, .venv): `pytest tests/test_cli.py` 25 passed; `ruff check src
tests/test_cli.py` clean; `mypy src` clean (8 files).

End to end (repo root, HEAD 5032f29, tree dirty):
- **Command shape, `--seconds`, output under `--out`:** `--schedule fast --seconds 5 --seed 1`
  exits 0 and writes `run.json`, `metrics.csv`, `crash_events.csv`, `queue/` and `crashes/`
  under `--out`. The run stops at elapsed 5.05 s (66 execs), so the budget is honoured with a
  single-execution overrun (ADR-0005 §2).
- **`run.json`:** it has all of `argv` (equal to the arguments passed), `config` (seeds_dir
  defaulted to `targets/seeds/tlv_parser`, max_execs null, timeout_s 1.0), `commit` (full HEAD
  hash), `dirty: true` (the tree has modified tracked files), `python`, `platform`,
  `started_at` (UTC), `seed_files` and `freeze_commit: null`. `seed_files` is exactly
  `[{"name": "S0", "sha256": "0a00d89f...d63be"}]`, which matches `targets/seeds/SHA256SUMS`
  for `tlv_parser/S0`.
- **`--seed` as the only randomness / replay (ADR-0005 §3):** run2 and run3 use the same
  seed with `--max-execs 300 --seconds 3600`. Both stop on max_execs with final `execs == 300`.
  With `elapsed_s` and `hang_time_s` dropped, `metrics.csv` (135 rows) is identical in full.
  With `elapsed_s` dropped, `crash_events.csv` (130 rows) is identical in full. `queue/` is
  byte-identical (`diff -r`), and so is every `crashes/*.bin` (`cmp`). The wall-clock-stopped
  run1 (final execs 66) also matches run2's prefix up to exec 66 in both streams, with run1's
  final stop-marker row left out, as §3 prescribes.
- **`--max-execs`:** 300 gives exactly 300 execs (above). `--max-execs 0` exits 2 with
  `max_execs must be >= 1, got 0`.
- **Error paths:** each exits 2 with no `Traceback`, and nothing is written under `--out`:
  - non-empty `--out`: names the path, and the pre-existing marker file is unchanged (md5
    equal, no new entries);
  - missing `--target`: `target targets/bin/nope does not exist or is not executable`, `--out`
    absent;
  - `--freeze-commit ""` and `--freeze-commit deadbeef`: `does not resolve to a commit (HEAD
    is 5032f290...)`, `--out` absent;
  - `--seconds 0` and `--timeout 0`: AFL-007's message naming the parameter, `--out` absent;
  - `--schedule rare`: argparse usage plus `invalid choice: 'rare' (choose from fast,
    uniform)`, `--out` absent.
- **`--freeze-commit HEAD`:** exits 0, and `run.json` `freeze_commit` is
  `5032f290ee378ca413ffe50fac7ec19dcde46edb` (40 chars, equal to `git rev-parse HEAD`).
- **Seeds and dirty-tree unit-only cases:** sorted order, `.DS_Store` and subdirectory
  skipping, missing/empty/hidden-only/subdir-only seeds dirs, `dirty` false/null, the
  side-branch freeze case and the abbreviated-hash freeze case are covered by the 25 passing
  tests. The reviewer verified them, and I did not repeat them end to end.
- **Packaging (lead decision, 2026-11-14: no network installs):** from `/tmp` with
  `PYTHONPATH=` empty, `.venv/bin/python -m fuzzer.cli --help` exits 0. `fuzzer` imports from
  the repo's `src/fuzzer/__init__.py`, and `pip show` reports an editable install at the repo
  root. `pyproject.toml` has `[build-system]` (setuptools>=61) and `packages.find
  where=["src"]`, and README documents `pip install -e .`. I did not run the fresh-venv check.

Experiment-validity notes (not blocking for a CLI ticket): with `--max-execs`, replay is exact
end to end, and the wall-clock prefix holds. In all three runs, every tlv_parser crash event
is signal 6 with `crash_site` `main`. Whether that site is the expected ground truth belongs
to AFL-010/AFL-013, not this ticket.

## Close (crew-lead, 2026-11-14)
DoD met: all 15 ACs ticked; reviewer approved after bounce 1 (both required changes resolved); tester PASS with gates green (test_cli.py 25 passed, ruff, mypy) and end-to-end runs on targets/bin/tlv_parser, including exact ADR-0005 §3 replay; Log complete. Recorded exceptions: the Packaging AC's fresh-venv check was not run (lead decision, 2026-11-14: no network installs; the editable install in .venv and `--help` from /tmp with an empty PYTHONPATH stand as evidence); verified in the working tree, not on a clean checkout; the target pre-check (lead decision) is not stated in an AC (reviewer note, optional follow-up). The AFL-008 commit is the human's. Closed → done.

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
- 2026-11-12 — ADR-0005 decisions: seed loading amended from "every file in DIR" to non-hidden regular files in `sorted()` order via AFL-007's shared function (a `.DS_Store`-only dir counts as empty); `run.json` gains `seed_files` (name + SHA-256, load order); `started_at` is provenance only; new AC: the parameter `ValueError` from `fuzzer.run(cfg)` validation surfaces as a non-zero exit with no traceback, before anything is written (human decision, 2026-11-12) (req-engineer)
- 2026-11-12 — only regular files are seeds: a subdirectory or other non-file entry is never loaded (AFL-007's `seed_files` filters on `p.is_file()`); tests added: "Seed files" (c) `S0` + `sub/` loads only `S0` and `seed_files` lists only `S0`, "Default and hard error" (e) a subdirectory-only dir counts as empty, same error as (b) (human decision, 2026-11-12) (req-engineer)
- 2026-11-14 — developer: implemented src/fuzzer/cli.py (argparse -> validate_config/seed_files/out/freeze checks, all before writing `run.json` or any execution -> `fuzzer.run`), `resolve_freeze_commit` helper, `[build-system]` (setuptools) + `src` package find in pyproject.toml, `pip install -e .` in README; tests/test_cli.py (22 tests, executor stubbed, git cases in temp repos). `pip install -e .` into .venv then `python -m fuzzer.cli --help` from /tmp exits 0. Gates: ruff clean on src + test_cli.py, mypy src clean; full pytest 289 passed, 1 failed (tests/test_toy_parser.py::test_ground_truth_and_source_docs, outside AFL-008 scope). Note: `pip install -e .` leaves untracked `src/greybox_fuzz_repro.egg-info/`, not gitignored (.gitignore out of my write scope).
- 2026-11-14 — developer: files changed: src/fuzzer/cli.py, tests/test_cli.py, pyproject.toml, README.md, .gitignore (added `*.egg-info/` so the editable-install `src/greybox_fuzz_repro.egg-info/` is not tracked; per orchestrator request).
- 2026-11-14 — reviewer: changes requested -> in-progress. `--freeze-commit` AC not met: (1) `--freeze-commit ""` fails open to `freeze_commit: null` (cli.py:81 truthiness test; needs `is not None` plus a test); (2) the resolve-failure message's "(HEAD checked)" is inaccurate (cli.py:37). All other ACs verified; gates green for AFL-008 scope (reviewer)
- 2026-11-14 — developer: bounce-1 fixes: `--freeze-commit` tested with `is not None` (empty value rejected, test case added); resolve-failure message now names the real HEAD hash or "unknown"; missing/non-executable `--target` is a pre-write check (exit 2, path named, nothing written; test_bad_target). tests/test_cli.py 25 passed, ruff and mypy clean.
- 2026-11-14 — reviewer: re-review of bounce-1 fixes: approved -> testing. Empty `--freeze-commit` now rejected (cli.py:86, test [empty]); resolve-failure message names HEAD's real hash or "unknown" (cli.py:37-40); target pre-check (lead decision) exits 2 before any write (cli.py:79-80, test_bad_target); autouse `target` fixture weakens no existing assertion. Nothing blocking. Gates green for AFL-008 scope (reviewer)
- 2026-11-14 — tester: PASS, ready to close. Gates green (25 passed, ruff, mypy). Real CLI on targets/bin/tlv_parser: run.json has all keys, seed_files = tlv_parser/S0 matching SHA256SUMS, dirty true; ADR-0005 §3 replay exact between two `--max-execs 300` runs (metrics.csv 135 rows, crash_events.csv 130 rows, queue and crashes/*.bin identical) and run1 prefix match under the wall-clock stop; error paths (non-empty --out, missing target, freeze ""/deadbeef, seconds/timeout/max-execs 0, bad schedule) each exit 2, no traceback, nothing written; --freeze-commit HEAD records the full hash; --help from /tmp with empty PYTHONPATH exits 0 (lead decision: no fresh venv). (tester)
- 2026-11-14 — closed (crew-lead): DoD verified; all ACs ticked, review approved after bounce 1, tester PASS, Log complete; fresh-venv packaging check waived by lead decision (no network installs); testing → done (crew-lead)
