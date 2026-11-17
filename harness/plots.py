"""Plotting. [implements FR-8 / ticket AFL-014]

Coverage-over-time and unique-crashes-over-time, UNIFORM vs FAST, with a median line and an
inter-trial IQR band per arm (Klees: report variance across trials, never a single run).

Reads persisted results only; runs no fuzzing. Usage: `python harness/plots.py results/`.
Each trial's step function is resampled onto a 1 s grid [0, seconds], carrying the last value
forward, then percentiles are taken across trials (proposed defaults, AFL-014 notes).
Before a trial's first sample, edges take the first value (the first row is ticked within
milliseconds of the S0 run) and crashes take 0; this differs from aggregate.edges_auc, which
uses 0 before the first row (negligible numeric gap).
Output: `<results>/figures/<target>_coverage.png`, `<target>_unique_crashes.png`.
"""
from __future__ import annotations

import csv
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aggregate
import dedup

Trial = tuple[Path, dict[str, Any]]
METRICS = {"edges": "coverage", "unique_crashes": "unique_crashes"}
LABELS = {"edges": "edges covered", "unique_crashes": "unique crashes (deduped)"}
ARMS = ("uniform", "fast")
COLORS = {"uniform": "tab:blue", "fast": "tab:red"}


def resample(times: Sequence[float], values: Sequence[float], grid: np.ndarray) -> np.ndarray:
    """Step function (times -> values) on `grid`, last value carried forward; first value before t0."""
    idx = np.searchsorted(np.asarray(times, dtype=float), grid, side="right") - 1
    return np.asarray(values, dtype=float)[np.clip(idx, 0, None)]


def trial_series(trial_dir: Path, target: str, metric: str, budget: float = float("inf")
                 ) -> tuple[list[float], list[float]]:
    """(times, values) of one trial: edges from metrics.csv, crashes from the dedup buckets that
    aggregate.counted_buckets keeps (no sentinels, none first seen after `budget`). [AFL-033]"""
    if metric == "edges":
        with (trial_dir / "metrics.csv").open(newline="") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            raise ValueError(f"{trial_dir / 'metrics.csv'} has no rows")
        return [float(r["elapsed_s"]) for r in rows], [float(r["edges"]) for r in rows]
    firsts = sorted(b.first_elapsed_s for b in aggregate.counted_buckets(
        dedup.bucket_trial(trial_dir, target), budget))
    return [0.0, *firsts], [float(i) for i in range(len(firsts) + 1)]


def plot_metric(trials: Sequence[Trial], target: str, metric: str, out: Path) -> None:
    """Median + IQR over trials per arm for one target; writes a PNG to `out`. [FR-8, AFL-014]

    `trials` are (trial_dir, run.json dict) pairs; those for other targets are ignored.
    """
    if metric not in METRICS:
        raise ValueError(f"unknown metric {metric!r}")
    mine = [(d, rj) for d, rj in trials if Path(rj["config"]["target"]).name == target]
    if not mine:
        raise ValueError(f"no trials for target {target!r}")
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for arm in ARMS:
        sel = [(d, rj) for d, rj in mine if rj["config"]["schedule"] == arm]
        if not sel:
            continue
        horizon = max(float(rj["config"]["seconds"]) for _, rj in sel)
        grid = np.arange(0.0, horizon + 1.0, 1.0)
        ys = np.array([resample(*trial_series(d, target, metric, float(rj["config"]["seconds"])),
                                grid) for d, rj in sel])
        q1, med, q3 = np.percentile(ys, [25, 50, 75], axis=0)
        ax.plot(grid, med, color=COLORS[arm], label=f"{arm.upper()} (n={len(sel)})")
        ax.fill_between(grid, q1, q3, color=COLORS[arm], alpha=0.25, linewidth=0)
    ax.set_xlabel("wall-clock time (s)")
    ax.set_ylabel(LABELS[metric])
    ax.set_title(f"{target}: median and IQR across trials")
    ax.legend()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)


def plot_all(trials: Sequence[Trial], results_dir: Path) -> list[Path]:
    """One coverage and one unique-crashes figure per target under `<results>/figures/`.

    Raises ValueError if the main campaign recorded aborts (Q11), is unfinished or has a
    trial cut short (aggregate.check_complete, AFL-033).
    """
    aggregate.check_complete(results_dir)
    kept = [(d, rj) for d, rj in trials if aggregate.is_main_trial(d, results_dir)]
    outs = []
    for target in sorted({Path(rj["config"]["target"]).name for _, rj in kept}):
        for metric, stem in METRICS.items():
            out = results_dir / "figures" / f"{target}_{stem}.png"
            plot_metric(kept, target, metric, out)
            outs.append(out)
    return outs


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: plots.py <results_dir>", file=sys.stderr)
        return 2
    results_dir = Path(args[0])
    try:
        outs = plot_all(aggregate.trial_dirs(results_dir), results_dir)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if not outs:
        print(f"error: no main-campaign trial under {results_dir}", file=sys.stderr)
        return 1
    for p in outs:
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
