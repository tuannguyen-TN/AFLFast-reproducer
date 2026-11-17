# Analysis provenance

The files in this directory are byte-identical copies of the outputs of the
main-campaign analysis. The analysis is final (lead decision, 2026-11-17).

- **Campaign.** `results/main`, run on the freeze commit
  `ff19bef7abb57b1ccbffd0318e2bbcb3c13f9cfc`, 2026-11-16T19:06:36Z to
  22:26:41Z: 3 targets x 2 schedules x 10 trials (seeds 1000 to 1009), 600 s
  each, concurrency 3.
- **Analysis code.** `ff19bef` plus the AFL-033 changes, committed with this
  snapshot. SHA-256 of the files as run:

  | file | SHA-256 |
  |---|---|
  | harness/aggregate.py | 8c91c7ea50303edd085736f54c2656a07877b7d61e177f9957cdb13ecee00086 |
  | harness/plots.py | 3577e24b7b3ab12a0ee3d72ef6343eaa39ad6146885646594758b2efbf437700 |
  | harness/dedup.py | bf6cb7d2d66e2101277511cdb645b718e744bdc80dc76d18fe6dc522fdba1e40 |
  | tests/test_aggregate.py | 7b6255666eca699f5de3f1395f65550f318572e93b19476f742b1ee5da759948 |
  | tests/test_plots.py | 2a24d27f718486b5a30ab1f588942d75e4a3d650c96ffdf1b1361ef1c1739e56 |

- **Commands.** Run once each from the repository root, both exit 0:
  `python harness/aggregate.py results/` at 2026-11-17T00:50:55Z, then
  `python harness/plots.py results/` at 2026-11-17T00:50:57Z.
- **Outputs.** `summary.md`, `summary.csv` and `trials.csv` here are
  `results/summary.md`, `results/summary.csv` and `results/trials.csv`;
  `figures/` is `results/figures/`.
- **H1, by the pre-registered rule (PRD §8).** Not supported: no primary
  member reaches Holm-adjusted p < 0.05. Every Holm-adjusted p is 1, and the
  smallest raw p is 0.5129.
- **Raw data.** Not in the repository (lead decision, 2026-11-17). The raw
  results are the archive `aflfast-results-ff19bef.tar.gz`, kept off the
  repository. `../../data/SHA256SUMS` lists the SHA-256 of every file in it,
  by repository-relative path, and on its last line the SHA-256 of the archive
  itself. To check, extract the archive in the repository root and run
  `shasum -a 256 -c data/SHA256SUMS` with the archive in that directory.
