---
id: AFL-037
title: Runner record fixes (AFL-031 review leftovers) and the fixture sha256 test (AFL-007 gap)
requirement: FR-7 / NFR-1
paper_ref: n/a
module: harness/run_campaign.py, tests/test_run_campaign.py, tests/ (one new test file for the fixture)
depends_on: [AFL-031]
status: done  # backlog|in-progress|review|testing|done
owner: developer                      # Sonnet develops, Opus reviews
---

## Goal
Fix the should-fix leftovers from the AFL-031 review (Log and review lines around
219-230 of tickets/done/AFL-031-stubbed-runner-tests-from-tester-scratch.md) and
close the AFL-007 fixture gap reported in AFL-035 (tickets/done/AFL-035-retune-tlv-parser-and-mini-format.md,
re-review of Must-fix 3, around line 68). Part of the AFL-011 freeze set (checklist
item (a)). Source: lead decision, 2026-11-16, items (b) and (i). Every test is stubbed:
no real launchctl, sysctl, clang or campaign runs.

## Acceptance criteria
- [x] **1. (MOST IMPORTANT) `_disabled` never turns an unknown into "not disabled".**
      The run metadata is evidence that the report cites, so a wrong `false` is worse
      than a `null`. Today any `launchctl print-disabled` token other than
      disabled/true maps to `false`. Required: only an explicit enabled/false token
      gives `false`; disabled/true gives `true`; an unrecognised token gives `null`;
      a failed command gives `null`. Stubbed test, one case per outcome above, plus a
      label that is not listed (stays as AFL-031 R3 decided: `false`).
- [x] **2. `start` sample before the symbolizer check.** The `start` crash-reporter
      sample is taken before `check_symbolizer`, because the symbolizer check itself
      crashes every bug's trigger once and so can cause `process: true` at start.
      Stubbed test: the order of calls (sample, then `check_symbolizer`) is asserted.
- [x] **3. `config_sha256` from the bytes parsed.** It is computed in preflight from the
      bytes actually parsed into the config, not after the probe from the file as it is
      then. Stubbed test: the config file is rewritten after preflight and before the
      record is written; the recorded hash equals the sha256 of the original bytes.
- [x] **4. Refusal text pinned.** The main-campaign refusal text carries "(dirty=...)"
      (introduced in AFL-031; the lead accepted it). Keep it; add a test that pins the
      text, and asserts the refusal still lists the modified tracked files, so AFL-011
      AC (a) still holds.
- [x] **5. `SubprocessError` handled.** `physical_cpus` and `_first_line` catch
      `subprocess.SubprocessError` (including `TimeoutExpired`). In `physical_cpus` it
      becomes a Refusal; in `_first_line` it becomes "unknown". No traceback. Stubbed
      test for each, raising `TimeoutExpired`.
- [x] **6. Fixture sha256 test.** A test asserts that the sha256 in the header of
      tests/fixtures/tlv_parser_asan_memcpy.txt equals sha256(targets/tlv_parser.c).
      This closes the AFL-007 gap: today a tlv_parser.c edit breaks no test.
- [x] **Mutant check.** Each fix's test fails on the unfixed code (applied by hand in a
      scratch copy, then restored); the Log names one mutant per AC 1-6.
- [x] **Gates.** `ruff check . && mypy src && pytest` are green.
- [x] **Scope.** `src/fuzzer/mutator.py` and `src/fuzzer/schedule.py` are unchanged
      (empty `git diff`). No other harness behaviour changes.
- [x] **No paths.** No home, scratch or temp path in any touched file.

## Technical notes (architect)
- Reuse the `root` fixture and `_cmd` stubs in tests/test_run_campaign.py. `ENV_ERRORS`
  already exists; AC 5 adds `SubprocessError` handling to the two helpers named there.
- Data-affecting (run record): Opus review.

## Test approach (tester)
Re-apply each mutant independently; confirm the stubs prevent any real launchctl, sysctl
or clang call; confirm the pre-freeze checklist (a) entry in tickets/testing/AFL-011-campaign-runner.md
lists this ticket.

## Review notes, round 2 (reviewer, Opus, 2026-11-16)
Verdict: APPROVE. I reviewed the full diff, not only the delta.

- M1 fixed. The `_disabled` regex is `"label"[ \t]*=>[ \t]*(\S*)`. A listed label always
  matches, any token outside {enabled, false, disabled, true} gives null (quoted and empty
  tokens included), and the match does not cross a newline. The unlisted label still gives
  false (AFL-031 R3), and a failed command gives null.
- S1 fixed. `test_start_sample_before_symbolizer_check` is parametrised over `--kind probe`
  and `--crash-probe`. Each run asserts the call order and that the recorded `start` is
  the first sample.
- N1. The developer's bounce-1 Log line says the four trailing boxes were ticked, but
  they were still unticked on re-submit. That Log line does not match the file. I ticked
  them now, after checking each box myself (evidence below).
- N2. Left alone, out of scope.
- Should-fix, non-blocking (test strength only, outside the ACs). The newline-crossing
  case in `test_disabled_tokens` (`'"x.L" =>'`, newline, `'"y.M" => disabled'`) does not
  pin `[ \t]*`. The mutant `\s*=>\s*(\S*)` survives it, because the crossed match takes
  `"y.M"`, which still maps to null. The case `('"x.L" =>\nenabled', 0, None)` would kill
  that mutant, which wrongly gives false. The code is correct, and real
  `launchctl print-disabled` output never puts a token on the next line. Left for a
  follow-up or for the tester; this does not block.
- Per criterion. AC 1-6 pass as in round 1. AC 2: one sample, taken before
  `check_symbolizer`, is passed to both record writers. AC 3: the hash is taken in
  preflight from the same bytes that are parsed.
- Mutants (scratch copy, each applied alone, then restored and verified): killed AC1
  old regex, unknown->false, failed->false, unlisted->null, enabled dropped from map;
  AC2 sample after symbolizer (both params), crash_probe re-samples (crash-probe param),
  campaign re-samples (probe param); AC3 hash at record time; AC4 "(dirty=...)" removed,
  file list removed; AC5 physical_cpus, _first_line; AC6 byte appended to tlv_parser.c.
  Survived: `\s*` with `(\S*)` (the should-fix above).
- Scope: `git diff -- src` is empty. No home, scratch or temp path in the diff or the new
  test file.
- Gates (real tree): ruff "All checks passed!"; mypy "Success: no issues found in 8 source
  files"; pytest "589 passed, 10 deselected in 103.72s (0:01:43)".

## Review notes, round 1 (reviewer, Opus, 2026-11-16)
Verdict: BOUNCE (one must-fix, AC 1).

Must-fix
- M1 (AC 1, harness/run_campaign.py:187). The regex `"label"\s*=>\s*(\w+)` does not
  match a listed label whose token is not a word (`=> "disabled"`, `=> -`, an empty
  token after `=>`), so `m` is None and the code takes the "unlisted" branch: the
  result is `false`. Checked on the current code with a stubbed `_cmd`: all three
  give False. That is an unknown turned into "not disabled", which AC 1 forbids. Also,
  `\s*` crosses newlines, so `"x.L" =>` followed by a newline and the next entry also
  gives False. Fix: `rf'"{re.escape(label)}"[ \t]*=>[ \t]*(\S*)'`. A listed label
  then always matches, and any token not in the map (an empty one included) gives
  None. Add the cases `('"x.L" => "disabled"', 0, None)` and `('"x.L" =>', 0, None)` to
  `test_disabled_tokens`. Verified in a scratch copy: with this fix and these cases,
  tests/test_run_campaign.py gives 174 passed. Real `launchctl print-disabled` output
  on macOS 26.5 (`"com.apple.ReportCrash" => disabled` / `=> enabled`) is unchanged
  by the fix.

Should-fix
- S1 (tests/test_run_campaign.py:1741). `test_start_sample_before_symbolizer_check`
  covers `--kind probe` only. The `--crash-probe` path shares the same call site, and
  `test_run_environment_recorded` already kills a mutant that re-samples inside
  `crash_probe`. Even so, a second parametrised run with `--crash-probe` that
  asserts the order and `crash_durations.json` `crash_reporters.start == {"n": 1}`
  would pin AC 2 on every path.

Nits
- N1. The Mutant check, Gates, Scope and No paths boxes are unticked, but the Log
  says they were done. Tick them on the re-submit.
- N2 (out of scope, no action here). The tests/fixtures/tlv_parser_asan_memcpy.txt
  header still says "(uncommitted)". The source has been committed in 30d7e98.

Per criterion
- AC 1: enabled/false give false, disabled/true give true, an unknown word gives
  null, a failed command (rc != 0 or ENV_ERRORS) gives null, and an unlisted label
  gives false. Fails only on the non-word token gap (M1). A null reaches
  campaign.json and crash_durations.json as JSON null. No reader in the harness
  interprets `disabled`, so nothing coerces it to false.
- AC 2: one call site (run(), before check_symbolizer, inside the Refusal try). The
  sample is a local and is passed to both record writers, so it cannot be stale or
  come from another run. A later refusal (output exists, run dir not empty) writes
  no record. Pass.
- AC 3: `raw` is read once. The same bytes are decoded and parsed, and also hashed.
  `load_yaml(path)` still re-reads the file when no `text` is given (3 test callers,
  unchanged). splitlines on decoded bytes gives the same lines as read_text's
  newline translation. main.yaml is ASCII. The 5-tuple has one caller (run). Pass.
- AC 4: the test pins "(dirty=True)" and " M .gitignore". Pass.
- AC 5: both helpers catch SubprocessError. physical_cpus raises a Refusal (exit 2,
  no traceback) and _first_line returns "unknown". Pass.
- AC 6: the regex matches the real header (`... sha256 <64 hex>` at the end of line
  1). It currently equals sha256(targets/tlv_parser.c) a3c01b3c...a99e. Pass.
- Scope: `git diff -- src` is empty. No other behaviour change, apart from the
  intended earlier start sample. No home, scratch or temp paths in the diff or the
  new test.
- Mutants (scratch copy, each applied on its own, all killed): AC1 unknown->False,
  failed->False, unlisted->None, enabled dropped from map; AC2 sample after
  symbolizer, crash_probe re-samples, campaign re-samples; AC3 hash at record time;
  AC4 "(dirty=...)" removed, file list removed; AC5 physical_cpus, _first_line;
  AC6 byte appended to tlv_parser.c.
- Gates (real tree): ruff "All checks passed!"; mypy "Success: no issues found in 8
  source files"; pytest "585 passed, 10 deselected in 109.64s (0:01:49)".

## Log
- 2026-11-16 — created (req-engineer), lead decision, 2026-11-16
- 2026-11-16 — implemented (developer). harness/run_campaign.py only. AC 1: `_disabled` maps enabled/false to false, disabled/true to true, any other token to null (failed command null, unlisted label false). AC 2: `run` samples `crash_reporters()` before `check_symbolizer` and passes it to `crash_probe` (new `start_reporters` arg) and to the campaign record. AC 3: `_preflight` hashes the config bytes it parses (`load_yaml` takes optional `text`) and returns the sha; `crash_probe` records it (new `cfg_sha256` arg). AC 4: text kept; pinned by test. AC 5: `physical_cpus` catches `SubprocessError` as Refusal, `_first_line` as "unknown". AC 6: tests/test_fixture_sha.py. Tests (tests/test_run_campaign.py, end): `test_disabled_tokens` (7 cases), `test_start_sample_before_symbolizer_check`, `test_config_sha256_is_of_bytes_parsed`, `test_main_refusal_text_pinned`, `test_physical_cpus_timeout_is_refusal`, `test_first_line_timeout_is_unknown`. No existing test adapted. Mutants, each applied in a scratch copy only and killed: AC1 unknown token `.get(..., False)`; AC2 sample after `check_symbolizer`; AC3 hash read from the file at record time; AC4 "(dirty=...)" removed from the refusal; AC5 `SubprocessError` dropped in `physical_cpus` and (separately) in `_first_line`; AC6 a line appended to a scratch copy of targets/tlv_parser.c. Gates: ruff clean, mypy src clean, pytest default suite all green (585 tests, 0 failed). src/ diff empty. (developer)
- 2026-11-16 — reviewed (reviewer, Opus): BOUNCE. Must-fix M1: `_disabled` returns false for a listed label with a non-word token (regex `(\w+)`). Should-fix S1, nits N1-N2. AC 2-6 pass. 13 mutants killed. Gates: ruff and mypy clean, pytest 585 passed, 10 deselected. (reviewer)
- 2026-11-16 — bounce 1 fixed (developer). M1: `_disabled` regex is now `"label"[ \t]*=>[ \t]*(\S*)`, so a listed label always matches and any token outside the map (empty or quoted included) gives null; `test_disabled_tokens` gains `=> "disabled"`, `=>` (empty) and a newline-crossing case (`"x.L" =>` then `"y.M" => disabled`), all null. Mutant (scratch copy, old regex `\s*=>\s*(\w+)`): the three new cases fail. S1: `test_start_sample_before_symbolizer_check` is parametrised over `--kind probe` and `--crash-probe`, asserting the order and `crash_reporters.start` equal to the first sample in campaign.json / crash_durations.json. N1: the four trailing boxes are ticked now, after this round's gates (ruff clean, mypy src clean, pytest default suite 589 passed, 10 deselected), empty `git diff -- src`, and no paths in the diff. N2: left alone (tests/fixtures out of scope). (developer)
- 2026-11-16 — review round 2: APPROVE (reviewer). M1 and S1 fixed; 15 mutants killed, 1 survived (newline-crossing test case, non-blocking should-fix). Gates: ruff and mypy clean, pytest 589 passed, 10 deselected. N1: the boxes were not ticked as the bounce-1 Log said; ticked by the reviewer after verifying. (reviewer)
- 2026-11-16 — review round 2 should-fix added: newline case pinning [ \t]* (developer; orchestrator decision, 2026-11-16)
- 2026-11-16 — tester: PASS (tester). AC 1-6 verified independently: `_disabled` mapping checked against all 11 `test_disabled_tokens` cases (including the added `"x.L" =>\nenabled` -> null); start sample precedes `check_symbolizer` at the single call site in run(), covering both `--kind probe` and `--crash-probe`; config hash taken from the parsed bytes in `_preflight`; refusal text "(dirty=True)" and file list pinned; SubprocessError handled in `physical_cpus` (Refusal) and `_first_line` ("unknown"); fixture header sha equals `shasum -a 256 targets/tlv_parser.c` (a3c01b3c...a99e). `git diff -- src` empty; no /Users, .claude/jobs or /private/tmp in the added lines or tests/test_fixture_sha.py. No timed run was active. Gates: ruff "All checks passed!"; mypy "Success: no issues found in 8 source files"; pytest "590 passed, 10 deselected in 104.68s (0:01:44)". Slow suite not run (not a target ticket). (tester)
- 2026-11-16 — DoD verified; closed via the gated mv (crew-lead)
