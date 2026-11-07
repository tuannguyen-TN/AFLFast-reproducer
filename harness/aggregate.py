"""Statistical aggregation. [implements FR-9 / ticket AFL-012]

Per metric (edges, unique crashes, time-to-first-crash):
  - median + IQR across trials
  - Mann-Whitney U test (UNIFORM vs FAST), report p-value
  - Vargha-Delaney A12 effect size
Crash counts use the honest dedup from dedup.py, NOT raw AFL "unique" counts.
"""
# TODO(AFL-012): implement aggregation + significance + effect size.
