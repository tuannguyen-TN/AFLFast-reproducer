---
id: AFL-025
title: Final report, part 2 (M4) — results with figures, final threats to validity, conclusion
requirement: G5, SC6, NFR-1 (consumes FR-6, FR-8, FR-9 outputs; PRD §8, §10 M4, §11, §12)
paper_ref: Klees CCS'18 (repeated trials, Mann-Whitney U, effect size, variance, crash de-duplication, reporting) | AFLFast CCS'16 (Fig. 11 'No Strategy', for context only; NG2)
module: docs/report/REPORT.md (S1 verdict sentence, S5 statistics paragraph, S6, S7 final, S8), docs/report/figures/
depends_on: [AFL-012, AFL-013, AFL-014, AFL-024]
status: done
owner: developer (drafts); human (final authorship and sign-off)
---

## Goal
Finish `docs/report/REPORT.md`, started by AFL-024, with everything that needs
main-campaign data: the results table and figures, the final threats to validity
and the conclusion. Report the campaign result honestly (SC6): a null result with
Klees-compliant statistics passes; overclaiming fails. Split from AFL-024 (human
decision, 2026-11-12).

Schedule: the campaign freeze (AFL-011) is targeted for Nov 18–19 and the final
deadline is 2026-11-22, so this ticket has about 3 days. AFL-024 must already
have closed (its sections written and re-checked at the freeze).

## Acceptance criteria

Additions to AFL-024's sections.
- [x] **S1 verdict and scale.** S1 gains a one-sentence verdict on H1 that matches
      S6 and S8. The planned scale AFL-024 stated (targets, trials per
      (target × schedule), per-trial budget) equals the campaign metadata of the
      main campaign; if not, S1 states the scale actually run.
- [x] **S5 statistics paragraph (in §5 Method).** States the analysis pre-registered in PRD §8
      (Analysis, H1; human decision, 2026-11-12) and implemented by AFL-012:
      median + IQR; a two-sided Mann-Whitney U test (U and p) at α = 0.05;
      A12(FAST, UNIFORM) as the direction and effect size (A12 > 0.5 means FAST's
      values tend to be larger); the primary family of six comparisons (final
      edges for each of the three targets, TTFC for each deep bug `toy-1`,
      `tlv-2`, `mfp-1`), corrected by Holm-Bonferroni, with significance only at
      Holm-adjusted p < 0.05; every other comparison exploratory and uncorrected
      (unique crashes, shallow-bug TTFC, coverage-curve area); final edges as the
      primary coverage measure and the area under the coverage-over-time curve
      as a secondary, exploratory one; and the censored-TTFC handling
      (right-censored at the budget, censored trials ranked as tied above every
      observed time, i.e. Gehan's generalized Wilcoxon test). It states that the
      family and the analysis were fixed before any pilot data existed.
      Clarification (lead decision, 2026-11-17): as implemented, censored TTFC
      uses Mann-Whitney U with censored trials ranked tied above every observed
      time, which AFL-012's Log records as equivalent to Gehan's generalized
      Wilcoxon test (`tickets/done/AFL-012-aggregation-stats.md`, Technical notes,
      "Censored TTFC (decided ...)": "with censored values ranked as ties above all
      observed values is equivalent to Gehan's generalized Wilcoxon test"); the
      report says "equivalent to" and does not claim a separate Gehan
      implementation.
- [x] **Vargha-Delaney magnitude labels (lead decision, 2026-11-17).** The report
      may label A12 magnitudes as an interpretation aid, explicitly marked "not
      pre-registered" and attributed to Vargha and Delaney (2000), symmetric about
      0.5: |A12 − 0.5| < 0.06 negligible, < 0.14 small, < 0.21 medium, otherwise
      large. The labels never change which rows are called significant.
- [x] **Exploratory paragraph (lead decision, 2026-11-17).** The mini_format
      unique-crashes row and the mfp-2 TTFC row get one paragraph in §6, labelled
      exploratory and hypothesis-generating, giving the uncorrected p of each and
      not calling either significant.
- [x] **S5 dedup paragraph re-checked.** AFL-024's de-duplication paragraph agrees
      with AFL-013 as implemented (and ADR-0003 if it exists). Any mismatch is
      fixed in REPORT.md.

Results.
- [x] **S6 Results, with the figures.**
      - A table with one row per (target × metric), for every target and every
        PRD §8 metric (edges covered, unique crashes deduped, TTFC per planted
        bug). Each row gives n per arm, median + IQR per arm, Mann-Whitney U, its
        p-value and A12, and is labelled primary or exploratory. Primary rows
        also give the Holm-adjusted p. TTFC rows also give the find rate k/n per
        arm.
      - Every number in the table equals the corresponding value in
        `results/summary.csv` of the main campaign. Check: the tester compares
        them cell by cell.
      - For every target, the coverage-over-time and unique-crashes-over-time
        figures from AFL-014 are included from their copies in
        `docs/report/figures/` (next AC). Each caption states n trials per arm
        and what the band is (e.g. IQR).
      - Any nonzero crash-site sentinel count flagged by AFL-012, and any
        unknown-crash bucket (`bug_id = None`), is reported with its count.
- [x] **Figure copies and provenance (human decision, 2026-11-12).** Every figure
      the report shows is a copy under `docs/report/figures/`; REPORT.md never
      links into `results/` (gitignored). Each copied figure's caption records the
      source path it was copied from (the results directory and file, e.g.
      `results/<campaign>/figures/<target>_coverage.png`), the full 40-character
      commit it was produced at, and the `plots.py` command. Checks: each copy's
      SHA-256 equals the SHA-256 of the file at its stated source path;
      `git check-ignore docs/report/figures/<file>` exits 1 for every copy (not
      ignored, so it can be committed).

Honesty (SC6, PRD §11).
- [x] A significant direction (FAST better or worse) is claimed for a primary row
      only when its Holm-adjusted p < 0.05, with the direction taken from A12.
      Every other primary row is described as "no statistically significant
      difference", whatever its medians or A12. An exploratory row is never called
      significant; any sentence about it is labelled exploratory and gives its
      uncorrected p. Check: every sentence in S1, S6 and S8 that asserts a
      significant direction cites a primary row whose Holm-adjusted p < 0.05.
      *(Changed 2026-11-12, following the human decision on PRD §8: was "only
      when that row's p < 0.05", which predates the Holm-corrected primary
      family.)*
- [x] H1 is given a verdict (supported / not supported / supported only for named
      target × metric rows) by applying PRD §8's H1 wording to the table, and the
      verdict is the same in S1, S6 and S8. If primary members are significant in
      both directions, the verdict is "mixed", with each endpoint's direction
      stated, and H1 is not described as supported overall (PRD §8 H1).
- [x] No claim about AFLFast as a whole (only the power schedule; PRD §8
      seed-selection deviation) and no comparison with AFLFast's absolute numbers
      (NG2).
- [x] A null result is reported as a null result, with the same statistics as any
      other row.

Threats and conclusion.
- [x] **S7 Threats to validity (final).** Every item of AFL-024's draft is still
      present, and every item it marked "AFL-025" is filled. Adds at least:
      measured throughput (execs/s) against NFR-3's 500 execs/s target, with the
      executor bottleneck named; the final number of comparisons under AFL-012's
      policy; and any campaign-time event (an aborted campaign, a flagged trial,
      a re-run) recorded in the campaign metadata. Also (lead decision,
      2026-11-17): the low-information point (deep bugs are rarely or never found:
      toy-1, tlv-2 and mfp-1 are mostly censored, so the TTFC endpoints carry
      little information) and the confirmation-pilot calibration lesson.
- [x] **S8 Conclusion (§8).** Restates the H1 verdict (identical to §1 and §6), the
      scale limitation, and what the result does and does not bear on (the power
      schedule alone). Names future work without claiming it (e.g. AFLFast's
      search strategy, binary-only instrumentation, NG5). Also (lead decision,
      2026-11-17): what would be needed to detect an effect: larger targets, longer
      budgets, a fork server, AFLFast's search strategy.

Reproducibility (NFR-1).
- [x] The table and every figure name the exact commit (full hash) and the exact
      command that produced them: the main-campaign command for the data, and the
      `aggregate.py` / `plots.py` commands for the table and the figures.
- [x] The freeze commit hash stated in S5 (AFL-024) equals the `freeze_commit` in
      every main-campaign `run.json`. The campaign commit the report states equals
      the `commit` in every main-campaign `run.json`, all with `dirty == false`.
- [x] Check: re-running the stated `aggregate.py` command at the stated commit on
      the stated results directory reproduces the report's table values exactly.

## Technical notes (architect)
- Fill AFL-024's skeleton; do not restructure it. Report structure (lead decision,
  2026-11-17): 1 Introduction; 2 Background; 3 Design and implementation; 4
  Development process; 5 Method; 6 Results; 7 Threats to validity; 8 Conclusion;
  Appendix A Provenance and reproduction. The statistics paragraph goes in §5,
  results in §6, threats in §7, conclusion in §8; the section labels "S1", "S5",
  "S6", "S7", "S8" in the ACs above map to §1, §5, §6, §7, §8. AFL-024 and AFL-025
  are committed in one commit. If writing results exposes a
  deviation not in PRD §8, PRD §8 is amended first through its own ticket (same
  rule as AFL-024 S4).
- Figure provenance lives in the caption, next to the figure, so a reader of the
  report sees it without opening another file. Copy with a byte-for-byte copy
  (`cp`), never re-export, so the SHA-256 check holds.
- `results/` is gitignored (AFL-015); `docs/report/figures/` is not.

## Test approach (tester)
Cell-by-cell table vs `results/summary.csv`. SHA-256 of each figure copy vs its
stated source. `git check-ignore` exits 1 on each copy. Every significant-direction
sentence cites a primary row with Holm-adjusted p < 0.05, and every sentence about an
exploratory row carries the exploratory label; the H1 verdict is identical in S1, S6 and S8. Freeze and
campaign hashes vs every main-campaign `run.json` (`freeze_commit`, `commit`,
`dirty`). Re-run the stated `aggregate.py` command and diff the table.

## Log
- 2026-11-12 — created (req-engineer), split from AFL-024 (human decision):
  results, figures, final threats to validity and conclusion; the S1 verdict and
  the S5 statistics paragraph moved here because they need AFL-012's decisions;
  figures copied into `docs/report/figures/` with per-figure provenance (results
  directory, commit, command) in the caption; direction/verdict honesty ACs and
  campaign-data reproducibility ACs moved here from AFL-024
- 2026-11-12 — statistics pre-registered (human decision, PRD §8 Analysis / H1):
  the S5 statistics paragraph AC now states the decided analysis (two-sided
  Mann-Whitney U, A12 direction, Holm-Bonferroni across the six-member primary
  family, exploratory rows uncorrected and labelled, final edges primary and
  coverage area exploratory, Gehan-style censored TTFC); the S6 table gains the
  primary/exploratory label and the Holm-adjusted p; the direction-claim honesty
  AC uses the Holm-adjusted p for primary rows (req-engineer)
- 2026-11-12 — H1 verdict AC gains the mixed-result case (primary members
  significant in both directions: verdict "mixed", each endpoint's direction
  stated, H1 not described as supported overall), following the human decision
  added to PRD §8 H1 (req-engineer)
- 2026-11-17 — aligned with AFL-024's new report structure and the lead's rulings
  (lead decision, 2026-11-17): Technical notes name the new structure; new ACs for
  Vargha-Delaney labels (not pre-registered) and the exploratory mini_format
  unique-crashes / mfp-2 TTFC paragraph; S7 gains the low-information point and the
  confirmation-pilot lesson; S8 gains what is needed to detect an effect; the
  statistics-paragraph AC clarifies the Gehan equivalence with a citation to
  AFL-012's Log. Report text written by the orchestrator from agent research
  (subagents may not write report files); lead decision, 2026-11-17 (req-engineer)
- 2026-11-17 — close check (tester): every AC PASS. docs/report/summary.csv, summary.md and trials.csv are identical to results/; all 15 table rows match cell by cell; the six figure copies match their stated sources by SHA-256 and are not ignored; all 60 main-campaign run.json have `freeze_commit` = `commit` = ff19bef7abb57b1ccbffd0318e2bbcb3c13f9cfc and `dirty` false; the S0 hashes equal `targets/seeds/SHA256SUMS` at ff19bef; the H1 verdict sentence is identical in §1, §6 and §8. Reproduction: `aggregate.py` re-run on a copy of results/main outside the repo gives a byte-identical summary.csv, summary.md and trials.csv. The stated command needs the README setup (`pip install -e .` in the venv) (orchestrator)
- 2026-11-17 — the report text was approved by the lead subject to edits A–G, recorded in AFL-024's Log (lead decision, 2026-11-17) (orchestrator)
- 2026-11-17 — DoD verified; closed via the gated mv (orchestrator)
