---
id: AFL-013
title: Crash de-duplication (crash-site bucketing)
requirement: FR-6
paper_ref: Klees § performance measures (crash de-duplication overcounts; ground truth)
module: harness/dedup.py
depends_on: [AFL-003]
status: backlog
owner: developer
---

## Goal
Save crashing inputs with enough context to bucket them by crash site, so that
"unique crashes" does not overcount bugs (FR-6, PRD §8). The heuristic must be
named, and its known overcounting bias stated, as Klees requires.

Open questions (PRD silent or ambiguous; resolve before leaving backlog):
- FR-6 says "PC / top-of-stack hash" but gives no stack depth N, and does not say
  whether to use the faulting PC alone or a hash of the top N frames.
- The PRD does not say where the "faulting context" comes from: the ASan report,
  a symbolized stack trace, or something else.
- FR-6 lists both `executor.py` and `dedup.py`. This ticket assumes saving crashes
  is in scope here, extending executor.py where needed, after AFL-003. Confirm.
- PRD §8(c) measures time-to-first-crash **per planted bug**. That needs a map
  from bucket to planted bug (ground truth). The PRD does not say how to build
  that map.

## Acceptance criteria
- [ ] Every crashing input is saved together with its terminating signal and
      faulting context.
- [ ] Crashes are bucketed by crash site (PC / top-of-stack hash, per FR-6).
- [ ] Two crashing inputs that hit the same crash site land in the same bucket.
- [ ] Crashing inputs at different crash sites land in different buckets.
- [ ] The unique-crash count reported equals the number of buckets.
- [ ] The heuristic is documented: named in the module docstring or README, with
      its known overcounting bias acknowledged (PRD §8, Klees).

## Technical notes (architect)
- **Placement (→ ADR-0003 (to write)):** dedup runs offline in `harness/`. fuzzer.py
  saves the crash files (format in AFL-007) and dedup.py reads them. The harness
  imports the fuzzer, never the reverse. This settles the split: the executor
  classifies and captures stderr (AFL-003), the fuzzer saves (AFL-007), dedup buckets
  (this ticket). executor.py needs no change here.
- **Interfaces (`harness/dedup.py`):**
  ```python
  @dataclass(frozen=True)
  class Bucket:
      key: str
      first_elapsed_s: float
      first_execs: int
      count: int
      example: Path
      bug_id: str | None          # from targets/ground_truth.json

  def parse_frames(asan_report: str, n: int = 3) -> tuple[str, ...]: ...
  def bucket_key(signal: int, asan_report: str) -> str: ...
  def bucket_trial(trial_dir: Path) -> list[Bucket]: ...   # sorted by first_elapsed_s
  ```
  aggregate.py (AFL-012) and plots.py (AFL-014) take unique crashes as `len(buckets)`
  and unique-crashes-over-time as a step function over `first_elapsed_s`.
- **Heuristic** (proposed default — confirm): key = signal + a hash of the top
  **N = 3** symbolized frames (`function file:line`) in the ASan report, skipping
  sanitizer-runtime and interceptor frames (`__asan_*`, `__interceptor_*`). If stderr
  holds no ASan stack, key = `"<signal>:nostack"`.
- **Faulting context:** the ASan report in `stderr` (`symbolize=1`, AFL-003). No
  separate debugger or symbolizer step.
- **Mapping to planted bugs** (proposed default — confirm): a bucket maps to bug B
  when the function and file of its top non-runtime frame match B in
  `targets/ground_truth.json` (AFL-009/010). Buckets that match nothing get
  `bug_id=None` and are reported as unknown crashes. Per-bug TTFC = the minimum
  `first_elapsed_s` over that bug's buckets.
- **Documentation (AC):** the module docstring names the "top-3-frame stack hash" and
  states Klees' finding that stack hashing overcounts (one bug, many stacks) and can
  also undercount. For planted bugs, the ground-truth mapping is the honest count.
- **AC1 wording:** "every crashing input is saved" conflicts with the AFL-007 storage
  filter (first crash per path_id). The filter never drops a bucket or delays its
  first time. If the filter is accepted, req-engineer should reword AC1.

## Test approach (tester)
Use distinct inputs that trigger the same planted bug and assert one bucket.
Use the toy_parser and tlv_parser bugs together and assert two buckets. Check
that the documentation is present.

## Log
- 2026-11-07 — created (req-engineer)
