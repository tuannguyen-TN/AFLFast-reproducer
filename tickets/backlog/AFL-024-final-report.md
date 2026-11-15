---
id: AFL-024
title: Final report, part 1 (M4) — results-free write-up (intro, background, design, deviations, method, draft threats to validity)
requirement: G5, NFR-1 (PRD §1, §4, §8, §10 M4, §12); SC6 is enforced in AFL-025
paper_ref: AFLFast CCS'16 (Markov-chain model, power schedules, §4.3, Fig. 11) | Klees CCS'18 (repeated trials, statistical tests, effect size, time budgets, crash de-duplication)
module: docs/report/REPORT.md (decided, human 2026-11-12; PDF question open, see Log)
depends_on: [AFL-011]   # close gate only (freeze commit); work may start now
status: backlog
owner: developer (drafts); human (final authorship and sign-off)
---

## Goal
Write the **results-free** part of the project report. **The report is the
deliverable; the code is the means.** It must answer the "too shallow" critique
(PRD §1, G5) by showing how greybox fuzzing and power schedules work, and how the
evaluation was designed. Everything here can be written before any main-campaign
data exists. Results, figures, the final threats to validity and the conclusion
are AFL-025 (split, human decision 2026-11-12).

Schedule: the final deadline is **2026-11-22** (PRD header). The campaign freeze
(AFL-011) is targeted for **Nov 18–19**, which leaves about **3 days** for
AFL-025. This ticket may start now so that those 3 days are spent on results only.
It **cannot close before the AFL-011 freeze**, because its deviation and method
sections are re-checked against the frozen tree (see the "Freeze re-check" AC).
That is why `depends_on` is `[AFL-011]`: a close gate, not a start gate.

**Location and format (decided, human 2026-11-12).** One Markdown file,
`docs/report/REPORT.md`. Whether the course needs a PDF is open (see Log);
Markdown can be converted at the end. The section skeleton S1–S8 is created here;
S6 and S8 are headed placeholders that AFL-025 fills.

## Acceptance criteria

Section ACs. The report has these top-level sections, in this order. S1–S5 and
S7 carry the content below. S6 (Results) and S8 (Conclusion) exist as headings
with a one-line placeholder naming AFL-025.

- [ ] **S1 Intro.** States: (a) the problem from PRD §1 (a prior report was too
      shallow); (b) hypothesis H1 as worded in PRD §8; (c) the planned scale:
      number of targets, trials per (target × schedule), and per-trial budget in
      seconds, each matching the frozen `experiments/configs/main.yaml` at the
      AFL-011 freeze commit (AFL-025 confirms it against the campaign metadata);
      (d) that the project reproduces the *direction* of AFLFast's result, not its
      absolute numbers (NG2). The H1 verdict sentence is added by AFL-025.
- [ ] **S2 Background, both papers.**
      - **AFLFast (CCS'16), the result reproduced.** Covers: the greybox loop
        (select a seed, assign energy, mutate it blindly that many times, execute,
        retain the input iff it reveals new coverage); the Markov-chain model
        (inputs exercise paths, and most generated inputs re-exercise a few
        high-frequency paths); energy and power schedules; the definitions of
        s(i) and f(i); the FAST schedule formula as stated in FR-5; and the claim
        that moving energy toward low-frequency paths finds bugs faster.
      - **Klees et al. (CCS'18), the evaluation standard.** Covers why
        single-run comparisons are untrustworthy (fuzzing is random), and the
        requirements this project adopts: multiple trials, Mann-Whitney U, an
        effect size (A12), a fixed and stated time budget, and crash
        de-duplication that can over- and under-count bugs (with ground truth
        as the honest count).
      - Each paper is cited with full bibliographic entry as in PRD §13.
- [ ] **S3 Design.** Contains:
      - an explicit statement of the mental model (CLAUDE.md §2): **coverage
        decides only which candidates are retained (FR-3) and, through the power
        schedule, how much energy each seed gets (FR-5). It never steers
        mutation (FR-4), which is blind.** AFLFast changes only the energy part;
      - an explicit statement that **the two arms differ only in
        `src/fuzzer/schedule.py`** (SC2, NFR-2), naming the evidence that
        enforces it: the schedule purity, RNG-ban and AST tests (AFL-006,
        AFL-023) and the mutator blindness test (AFL-005);
      - one short description per component (coverage bitmap via
        SanitizerCoverage shared memory, executor with timeout and signal
        classification, corpus, mutator, schedule, main loop), each naming its
        module path;
      - the initial corpus (`targets/seeds/<target>/S0`, identical in both arms)
        and the coverage granularity actually used in the main campaign
        (presence-only or hit-count buckets, per the AFL-011 pilot decision);
      - the three targets and their planted bugs, each bug with its id, its
        depth class (shallow / deep, PRD §8) and its crash-site function.
- [ ] **S4 Deviations.** Reuses PRD §8's deviations; it does not re-invent them.
      - Every numbered PRD §8 deviation, **(i) through (viii)**, appears exactly
        once, labelled with its PRD §8 numeral and the words "PRD §8". The
        report's wording does not contradict the PRD's.
      - The two unnumbered deliberate deviations in PRD §8 also appear, each
        exactly once, referred to **by name** (human decision, 2026-11-12), since
        PRD §8 gives them no numeral: **"PRD §8, seed-selection deviation"**
        (fixed round-robin in both arms; no favored-seed culling or skip
        probabilities; results bear on the power schedule alone, not AFLFast as a
        whole, with the AFLFast Fig. 11 'No Strategy' note) and **"PRD §8,
        deterministic-stage deviation"** (deterministic stage dropped in both
        arms, AFLFast §4.3). The report does not invent numerals for them.
      - (viii) is presented as PRD §8 presents it: a deviation from the paper's
        eq. 4, not from AFLFast's code.
      - The section lists no deviation that is absent from PRD §8. If writing
        finds a new one, PRD §8 is amended first through its own ticket.
      - Check: a reviewer maps each item in S4 to one PRD §8 item, one to one,
        with none missing and none extra: (i)–(viii) by numeral, the other two by
        name, ten in total.
- [ ] **S5 Experimental method.** States:
      - **Pre-registration and freeze:** the retuning rule and the
        coverage-granularity fallback (AFL-011), and that their thresholds were
        fixed before any pilot data existed; the first-pilot numbers, whether
        each trigger fired, any target retuned (with its first-pilot numbers) and
        the confirmation-pilot results if one ran, each taken from
        `results/pilot/`; that pilot, confirmation-pilot and main seeds are
        pairwise disjoint; and the **freeze commit hash** (full 40 characters);
      - trial count per (target × schedule), seeds (`base_seed + i`), and the
        per-trial budget, as set in the frozen `experiments/configs/main.yaml`;
      - **censoring of time-to-first-crash:** a planted bug not found in a trial
        is right-censored at the budget, never dropped and never clamped; TTFC is
        reported as find rate k/n plus median, with "> budget" when more than
        50 % of an arm's trials are censored. (The name of the censoring-aware
        test is added by AFL-025, once AFL-012 has fixed it.)
      - **crash de-duplication:** the heuristic is named as PRD §8 and AFL-013
        define it (crash site = first in-target stack frame of the ASan report;
        ADR-0003 if it exists by then); its overcounting bias (one bug, many
        stacks) and merge bias (two bugs in one function) are both stated; the
        mapping of buckets to planted bugs (ground truth,
        `targets/ground_truth.json`) is described; and sentinel / unknown buckets
        (AFL-007) are explained. AFL-025 re-checks this paragraph against AFL-013
        as implemented.
      - The statistics paragraph (tests, sidedness, multiple-comparison policy,
        coverage scalar) is **not** in this ticket: it depends on AFL-012's
        decisions and is written under AFL-025.
- [ ] **S7 Threats to validity (draft).** A draft that covers at least: small
      targets; short budget (the frozen `seconds_per_trial` vs AFLFast's 24 h); a
      single machine; planted bugs as ground truth; dedup biases; timeouts as the
      one timing-dependent exception to replay (ADR-0005); the platform used (OS
      and compiler, ADR-0001). It also discloses, where they happened before the
      freeze: any `--allow-fewer-targets` override and its reason (AFL-011), any
      target retune, and a granularity switch. Items that need campaign data
      (measured throughput, final number of comparisons, campaign-time events)
      are marked "AFL-025" in the draft and finalised there.

Scope, honesty and reproducibility for the results-free part.
- [ ] **No results.** At close, REPORT.md contains no main-campaign number, no
      claimed direction (FAST better or worse) and no H1 verdict. S6 and S8 hold
      only their placeholders. Check: grep finds no reference to a main-campaign
      results directory or `summary.csv` value in S1–S5 or S7.
- [ ] **No overclaim in background and design (SC6, PRD §11).** No claim about
      AFLFast as a whole (only the power schedule; PRD §8 seed-selection
      deviation) and no comparison with AFLFast's absolute numbers (NG2).
- [ ] **Freeze hash (NFR-1).** S5 states the freeze commit hash in full (40
      characters). It equals the hash in AFL-011's freeze Log entry. (AFL-025
      checks it against `freeze_commit` in every main-campaign `run.json`.)
- [ ] **S0 and config (NFR-1).** The report states the SHA-256 of each target's
      S0, matching `targets/seeds/SHA256SUMS` at the freeze commit, and the config
      path (`experiments/configs/main.yaml`).
- [ ] **Freeze re-check (human decision, 2026-11-12).** Before this ticket
      closes, every deviation section (S4, plus each deviation mentioned in S3 or
      S7) is re-checked against PRD §8 **as of the AFL-011 freeze commit**
      (`git show <freeze_commit>:docs/PRD.md`). Any mismatch is fixed in REPORT.md
      (or, for a new deviation, PRD §8 is amended first through its own ticket).
      The Log records the freeze hash used and the result of the check. This
      ticket does not move to done before AFL-011's Log records the freeze hash.

## Technical notes (architect)
- Location and format decided (human, 2026-11-12): `docs/report/REPORT.md`,
  Markdown. If a PDF is needed it is a conversion at the end (open Log item), not
  a second source.
- Create the full S1–S8 skeleton here so AFL-025 only fills S6, S8, the S1 verdict
  sentence, the S5 statistics paragraph and the AFL-025 items in S7.
- PRD §8 deviation labels: "(i)"–"(viii)" with "PRD §8", and the two unnumbered
  ones by name: "seed-selection deviation" and "deterministic-stage deviation".
- Figures and tables belong to AFL-025 (copied into `docs/report/figures/`).

## Test approach (tester)
One-to-one S4 ↔ PRD §8 mapping, run against `git show <freeze_commit>:docs/PRD.md`
(ten items: eight numbered, two named). Freeze hash in S5 vs AFL-011's freeze Log
entry. S0 hashes vs `targets/seeds/SHA256SUMS` at the freeze commit. Grep for
results content (main-campaign paths, direction words such as "outperforms" or
"significant" applied to this project's data, an H1 verdict) in S1–S5 and S7.
Confirm the Log records the freeze re-check.

## Log
- 2026-11-12 — created (req-engineer) per human decisions (2026-11-12): purpose,
  sections, honesty, reproducibility, schedule (deadline 2026-11-22, freeze Nov
  18–19), location/format as proposed default. depends_on AFL-012 and AFL-014 named
  by the human; **AFL-013 added by the orchestrator**, because the results need
  de-duplicated crash counts and AFL-013 is not a transitive dependency of AFL-012
  or AFL-014 in their `depends_on` lists.
- 2026-11-12 — open (req-engineer): how to label PRD §8's two unnumbered
  deliberate deviations (seed selection, deterministic stage) for cross-reference,
  since only (i)–(viii) carry numbers. Needs a human / PRD decision before this
  ticket leaves backlog.
- 2026-11-12 — split (human decision): this ticket is now the results-free part
  (S1 without verdict, S2–S5 without the statistics paragraph, S7 draft); S6,
  S8, the S1 verdict, the S5 statistics paragraph, final S7, figures, the
  direction/verdict honesty ACs and the campaign-data reproducibility ACs moved
  to AFL-025. depends_on changed from [AFL-012, AFL-013, AFL-014] to [AFL-011]
  (close gate: freeze). Added the "Freeze re-check" AC (req-engineer)
- 2026-11-12 — resolved the open item above (human decision): the two unnumbered
  PRD §8 deviations are referred to by name, "PRD §8, seed-selection deviation"
  and "PRD §8, deterministic-stage deviation"; no numerals invented (req-engineer)
- 2026-11-12 — module decided: `docs/report/REPORT.md`, Markdown (human decision).
  **Open:** human to confirm whether the course wants a PDF; Markdown can be
  converted at the end (req-engineer)
