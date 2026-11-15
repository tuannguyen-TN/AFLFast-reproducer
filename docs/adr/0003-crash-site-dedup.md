# ADR-0003: Crash de-duplication by first in-target frame

- **Status:** accepted
- **Date:** 2026-11-14
- **Owner:** architect
- **Related:** AFL-013, AFL-007, FR-6, PRD section 8, ADR-0005 section 3

## Context
FR-6 says dedup buckets by "crash site (PC / top-of-stack hash)" but gives no
stack depth and no source of the faulting context. Klees et al. show that
stack-based dedup misstates bug counts, so the heuristic must be fixed, named and
its biases stated.

## Options considered
1. Faulting PC alone — varies with ASLR and build, not replay-safe.
2. Hash of the top N frames — needs an arbitrary N; overcounts one bug reached
   from several call stacks.
3. First in-target stack frame (function name) — stable across processes, one
   key per planted bug when each bug sits in its own function.

## Decision
- **"PC / top-of-stack" means the first in-target stack frame**: the function of
  the first frame of the first ASan stack whose source file is the target's. It is
  computed once, by AFL-007's shared extractor `fuzzer.fuzzer.crash_site`, and
  stored in the `crash_site` column of `crash_events.csv`.
- **The key is the site only.** The signal is not part of it; no top-N hash.
- **Source is the event stream.** `harness/dedup.py::bucket_trial` buckets every
  row of `crash_events.csv`. Saved inputs (`saved` column) are only replay
  examples, never counted. dedup.py has no frame-parsing code, so event-stream
  time-to-first-crash and dedup counts agree on the site.
- **Placement.** dedup runs offline in `harness/`; the harness may import the
  fuzzer, never the reverse. The executor classifies, the fuzzer extracts and
  saves, dedup buckets.
- **Sentinels.** `"no_stack"`, `"unsymbolized"`, `"no_target_frame"` each get
  their own bucket with `bug_id=None`, reported as unknown crashes, never merged
  with a real-site bucket or each other.
- **Ground-truth mapping.** A real-site bucket maps to bug B when the site equals
  B's `function` in `targets/ground_truth.json` (looked up only among the trial's
  target's bugs; `target` is required, and a target with no entry raises). Everything else is `bug_id=None`. Per-bug TTFC = minimum
  `first_elapsed_s` over that bug's buckets.
- **`crash_site` is process-invariant (binding; enforces ADR-0005 section 3,
  "`crash_site` is replay-safe").** The format contains no absolute address, no
  PID and no path, so identical crashes in different processes give the same
  string. Any change to the extractor or this key must keep it free of
  process-varying content, or exec-index replay breaks. Tested on toy-2's
  trigger `b"!aaa"` run in two separate processes.
- **A missing symbolizer gives `no_target_frame` (moved here from ADR-0005
  section 3).** `crash_site()` returns `"unsymbolized"` only when no frame of the
  first stack has a function name. When some frames have names but none is in the
  target's source file, it returns `"no_target_frame"`. Without a working
  symbolizer the ASan runtime and system-library frames can still have names, but
  the target's frames have no `file:line`; that report is labelled
  `"no_target_frame"`, not `"unsymbolized"`. A target built without `-g` gets the
  same label: `-g` is in the Makefile's overridable `CFLAGS`, not in
  `REQUIRED_FLAGS`. So `"no_target_frame"` does not tell "symbolization failed" apart
  from "crashed outside the target". AFL-011's pre-flight symbolizer check covers
  this: one known trigger per planted bug must make `crash_site()` return that
  bug's `function`, or the campaign aborts.

## Consequences
- Known biases, disclosed in the `dedup.py` docstring: one bug reached via
  several sites overcounts; two bugs in one function merge (hence one planted bug
  per function). For planted bugs the ground-truth mapping is the honest count.
- Sentinel buckets inflate the unique-crash count if symbolization breaks;
  AFL-012 flags nonzero sentinel counts.
- Interface for AFL-012/AFL-014: `bucket_trial(trial_dir, target)` (AFL-012/014 pass the trial's target); unique
  crashes = `len(buckets)`.
