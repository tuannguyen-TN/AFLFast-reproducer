"""Crash de-duplication by crash site. [implements FR-6 / ticket AFL-013; ADR-0003]

Heuristic (named): **first in-target stack frame**. Every row of a trial's
`crash_events.csv` is bucketed by its `crash_site` column, which AFL-007's shared
extractor (`fuzzer.fuzzer.crash_site`) fills with the function of the first frame
of the ASan stack that lies in the target's source file. This module uses that
value verbatim and has no frame-parsing logic of its own. The signal is not part
of the key. The three extractor sentinels ("no_stack", "unsymbolized",
"no_target_frame") each get their own bucket, never merged with a real site or
with each other, and are reported as unknown crashes (`bug_id=None`).

Known biases (Klees et al., "Evaluating Fuzz Testing", crash de-duplication):
- Stack-based bucketing can overcount (one bug reached through several sites).
- Two bugs in one function merge into one bucket (site = function). This is why
  every planted bug sits in its own function (PRD section 8).
For planted bugs the ground-truth mapping (`Bucket.bug_id`) is the honest count.
"""
import csv
import json
from dataclasses import dataclass
from pathlib import Path

from fuzzer.fuzzer import SENTINELS

GROUND_TRUTH = Path(__file__).resolve().parent.parent / "targets" / "ground_truth.json"


@dataclass(frozen=True)
class Bucket:
    key: str  # crash_site (real site or sentinel)
    first_elapsed_s: float
    first_execs: int
    count: int
    example: Path | None  # earliest non-empty `saved` of the bucket, as in the CSV
    bug_id: str | None  # from targets/ground_truth.json; None for unknown/sentinel


def bucket_trial(trial_dir: Path, target: str,
                 ground_truth: Path = GROUND_TRUTH) -> list[Bucket]:
    """Bucket every event of `<trial_dir>/crash_events.csv` by `crash_site`.

    Sorted by `first_elapsed_s`. `target` (e.g. "toy_parser", the trial's target)
    is required: bug_id is looked up only among that target's planted bugs, since
    function names such as `main` recur across targets. A target with no entry in
    the ground truth raises ValueError. A real site maps to bug B when it equals
    B's `function` (exact name; the file is implied by the target); sentinels and
    unmatched sites get `bug_id=None`.
    """
    truth = json.loads(ground_truth.read_text())
    funcs = {b["function"]: bid for bid, b in truth.items() if b["target"] == target}
    if not funcs:
        raise ValueError(f"target {target!r} has no entry in {ground_truth}")
    first: dict[str, tuple[float, int]] = {}
    counts: dict[str, int] = {}
    examples: dict[str, Path] = {}
    with (trial_dir / "crash_events.csv").open(newline="") as f:
        for row in csv.DictReader(f):
            k = row["crash_site"]
            elapsed, execs = float(row["elapsed_s"]), int(row["execs"])
            if k not in first or (elapsed, execs) < first[k]:
                first[k] = (elapsed, execs)
            counts[k] = counts.get(k, 0) + 1
            if row["saved"] and k not in examples:  # rows are in time order
                examples[k] = Path(row["saved"])
    buckets = [Bucket(k, first[k][0], first[k][1], counts[k], examples.get(k),
                      None if k in SENTINELS else funcs.get(k)) for k in counts]
    return sorted(buckets, key=lambda b: (b.first_elapsed_s, b.first_execs))
