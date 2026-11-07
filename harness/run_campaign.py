"""Experiment runner. [implements FR-7 / ticket AFL-011]

Runs N independent trials per (target x schedule) with a fixed wall-clock
budget and a distinct RNG seed per trial, writing per-trial metrics to
results/. This is the Klees-compliant backbone: repeated trials, not one run.
"""
# TODO(AFL-011): load experiments/configs/*.yaml, loop trials, persist metrics.
