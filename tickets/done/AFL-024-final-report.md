---
id: AFL-024
title: Final report, part 1 (M4) — results-free write-up (intro, background, design, deviations, method, draft threats to validity)
requirement: G5, NFR-1 (PRD §1, §4, §8, §10 M4, §12); SC6 is enforced in AFL-025
paper_ref: AFLFast CCS'16 (Markov-chain model, power schedules, §4.3, Fig. 11) | Klees CCS'18 (repeated trials, statistical tests, effect size, time budgets, crash de-duplication)
module: docs/report/REPORT.md (decided, human 2026-11-12; PDF question open, see Log)
depends_on: [AFL-011]   # close gate only (freeze commit); work may start now
status: done
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
Markdown can be converted at the end. The section skeleton (S1–S8 and Appendix A,
below) is created here; §6 and §8 are headed placeholders that AFL-025 fills.

**Report structure (lead decision, 2026-11-17).** The top level of
`docs/report/REPORT.md`, in this order: 1 Introduction; 2 Background (AFLFast's
claim, and Klees et al.'s standard); 3 Design and implementation; 4 Development
process; 5 Method (pre-registered analysis, campaign procedure, deviations
table); 6 Results; 7 Threats to validity; 8 Conclusion; Appendix A Provenance and
reproduction. AFL-024 and AFL-025 are drafted together and committed in one commit
(lead decision, 2026-11-17).

## Acceptance criteria

Section ACs. The report has the top-level sections above, in this order (lead
decision, 2026-11-17). §1, §2, §3, §4, §5, §7 and Appendix A carry the content
below. §6 (Results) and §8 (Conclusion) are filled by AFL-025. Below, "S1", "S2",
"S3", "S5", "S7" keep their old labels for the content ACs that were written
under them; they are report sections §1, §2, §3, §5, §7.

- [x] **S1 Intro (§1).** States: (a) the problem from PRD §1 (a prior report was too
      shallow); (b) hypothesis H1 as worded in PRD §8; (c) the planned scale:
      number of targets, trials per (target × schedule), and per-trial budget in
      seconds, each matching the frozen `experiments/configs/main.yaml` at the
      AFL-011 freeze commit (AFL-025 confirms it against the campaign metadata);
      (d) that the project reproduces the *direction* of AFLFast's result, not its
      absolute numbers (NG2). The H1 verdict sentence is added by AFL-025.
- [x] **S2 Background, both papers (§2: AFLFast's claim, and Klees et al.'s standard).**
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
- [x] **S3 Design and implementation (§3; renamed, lead decision, 2026-11-17).** Contains:
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
- [x] **§4 Development process (new, lead decision, 2026-11-17).** Fourteen
      phases, in this order, each stating what was done and why: Scoping,
      Guardrails, Spike, Engine, Pre-registration, Targets, Delegation, Timing
      probe, First pilot, Confirmation pilot, Freeze, Campaign, Analysis,
      Wrap-up. Each fact traces to a ticket Log entry, a commit, an ADR or a PRD
      line; where a reason is the lead's rationale and is not recorded in the
      repo, the text attributes it as such ("the lead's rationale, not recorded
      in the repo"). Check: the reviewer picks each phase's facts and finds the
      cited source; no phase is missing or merged.
- [x] **S4 Deviations, now a deviations table under §5 Method (lead decision,
      2026-11-17; sub-requirements unchanged).** Reuses PRD §8's deviations; it
      does not re-invent them.
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
      - Check: a reviewer maps each item in the deviations table to one PRD §8
        item, one to one, with none missing and none extra: (i)–(viii) by numeral,
        the other two by name, ten in total.
- [x] **S5 Experimental method (§5 Method: pre-registered analysis, campaign
      procedure, deviations table; stays under §5, lead decision, 2026-11-17).**
      States:
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
- [x] **S7 Threats to validity (§7; draft).** A draft that covers at least: small
      targets; short budget (the frozen `seconds_per_trial` vs AFLFast's 24 h); a
      single machine; planted bugs as ground truth; dedup biases; timeouts as the
      one timing-dependent exception to replay (ADR-0005); the platform used (OS
      and compiler, ADR-0001), with the versions taken from the machine record in
      `results/main/campaign.json` (model, macOS, clang, core counts) rather than
      "confirm against metadata" (lead decision, 2026-11-17); coverage-instrumentation fragility: SanitizerCoverage's
      default block pruning can drop the guard of a crashing block once that block
      gains a branch, so the last step of a crash-ending staircase (tlv_parser,
      mini_format) depends on the exact source; the shipped sources were checked by
      the slow staircase tests and targets/ is frozen at the AFL-011 freeze, so the
      measured campaign is unaffected, but the deep-bug staircases do not transfer to
      edited sources (AFL-010 tester finding F2). It also discloses, where they happened before the
      freeze: any `--allow-fewer-targets` override and its reason (AFL-011), any
      target retune, and a granularity switch. It also carries the five AFL-035
      retune disclosures (lead decision, 2026-11-16 (g)), one sentence each:
      (1) tlv-2 has a direct route S1 to crash (about 7.2e-4 per mutant, arithmetic on
      the 16-bit window 59 00 to 58 xx), so its effective expected cost is about 1,570,
      not the staircase sum of about 2,650 (2,439 on the Log's one seed);
      (2) mfp-1 has a parallel route, the T record before ver 2 (S0 with AB to 54 is
      retained under ver 1), at about 2.8e-3;
      (3) mfp-2 has four single-byte triggers (len 05..08), not two;
      (4) the mfp S0 covers 13 edges, not 17, because it no longer parses its B record;
      (5) both retuned S0s carry a hand-placed dormant record next to the bug, so
      depth is relative to these seeds (arm-neutral, but the targets changed).
      It also discloses the confirmation-pilot lesson (lead decision, 2026-11-16): the retune
      target (an expected 1,500–3,000 mutants of the staircase seed) did not account for
      round-robin splitting the budget across the corpus (the lead's calibration error); with
      mini_format's corpus at about 37 seeds, mfp-1's effective cost is far above the per-trial
      budget, it was never found in the confirmation pilot, no second retune is allowed, and its
      endpoint is expected to be mostly censored. Items that need campaign data
      (measured throughput, final number of comparisons, campaign-time events)
      are marked "AFL-025" in the draft and finalised there.

- [x] **Appendix A Provenance and reproduction (new, lead decision, 2026-11-17).**
      States: the freeze commit (full 40 characters); the campaign command; the
      analysis commands (`aggregate.py`, `plots.py`); the S0 SHA-256 hashes; and
      the `data/SHA256SUMS` check (extract the raw-data archive into a fresh empty
      directory, copy `data/SHA256SUMS` and the archive there, run
      `shasum -a 256 -c SHA256SUMS`). It is consistent with the README Quickstart
      and with `docs/report/PROVENANCE.md`. Check: the reviewer diffs the commands
      and hashes against both files.

Scope, honesty and reproducibility.
- [x] **Results-bearing statements (replaces "No results", lead decision,
      2026-11-17).** AFL-024 and AFL-025 are drafted together and committed in one
      commit. Results-bearing statements (a main-campaign number, a direction or
      the H1 verdict) are allowed only in: the §1 verdict sentence; the Campaign,
      Analysis and Wrap-up phases of §4; the AFL-025 items of §7; §8; Appendix A;
      and §6. Each such number equals the corresponding value in
      `docs/report/summary.csv` or the main campaign metadata. Check: grep for
      main-campaign numbers, direction words ("outperforms", "significant") and
      the verdict in §2, §3, §5 and the other phases of §4 finds nothing.
- [x] **No overclaim in background and design (SC6, PRD §11).** No claim about
      AFLFast as a whole (only the power schedule; PRD §8 seed-selection
      deviation) and no comparison with AFLFast's absolute numbers (NG2).
- [x] **Freeze hash (NFR-1).** §5 states the freeze commit hash in full (40
      characters). It equals the hash in AFL-011's freeze Log entry. (AFL-025
      checks it against `freeze_commit` in every main-campaign `run.json`.)
- [x] **S0 and config (NFR-1).** The report states the SHA-256 of each target's
      S0, matching `targets/seeds/SHA256SUMS` at the freeze commit, and the config
      path (`experiments/configs/main.yaml`).
- [x] **Freeze re-check (human decision, 2026-11-12).** Before this ticket
      closes, every deviation section (the §5 deviations table, plus each deviation mentioned
      in §3, §4 or §7) is re-checked against PRD §8 **as of the AFL-011 freeze commit**
      (`git show <freeze_commit>:docs/PRD.md`). Any mismatch is fixed in REPORT.md
      (or, for a new deviation, PRD §8 is amended first through its own ticket).
      The Log records the freeze hash used and the result of the check. This
      ticket does not move to done before AFL-011's Log records the freeze hash.

## Technical notes (architect)
- Location and format decided (human, 2026-11-12): `docs/report/REPORT.md`,
  Markdown. If a PDF is needed it is a conversion at the end (open Log item), not
  a second source.
- Create the full skeleton here (§1–§8 and Appendix A, structure as in the Goal,
  lead decision, 2026-11-17) so AFL-025 only fills §6, §8, the §1 verdict sentence,
  the §5 statistics paragraph and the AFL-025 items in §7, §4 (Campaign, Analysis,
  Wrap-up) and Appendix A.
- PRD §8 deviation labels: "(i)"–"(viii)" with "PRD §8", and the two unnumbered
  ones by name: "seed-selection deviation" and "deterministic-stage deviation".
- Figures and tables belong to AFL-025 (copied into `docs/report/figures/`).

## Test approach (tester)
One-to-one §5 deviations table ↔ PRD §8 mapping, run against
`git show <freeze_commit>:docs/PRD.md` (ten items: eight numbered, two named).
Freeze hash in §5 vs AFL-011's freeze Log entry. S0 hashes vs
`targets/seeds/SHA256SUMS` at the freeze commit. Grep for results content
(main-campaign numbers, direction words such as "outperforms" or "significant"
applied to this project's data, an H1 verdict) outside the places the
results-bearing AC allows. §4: each of the 14 phases has a cited source. Appendix A
vs README and `docs/report/PROVENANCE.md`. Confirm the Log records the freeze
re-check.

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
- 2026-11-15 — threats to validity: added SanitizerCoverage block-pruning fragility of crash-ending staircases (AFL-010 F2); no ticket for it (lead decision, 2026-11-15) (req-engineer)
- 2026-11-16 — threats to validity: added the five AFL-035 retune disclosures (lead decision, 2026-11-16) (req-engineer)
- 2026-11-16 — threats to validity: added the confirmation-pilot calibration lesson for mfp-1 (lead decision, 2026-11-16) (orchestrator)
- 2026-11-17 — report text written by the orchestrator from agent research (subagents may not write report files); lead decision, 2026-11-17 (orchestrator)
- 2026-11-17 — ACs restructured to the lead's report structure (lead decision, 2026-11-17): top level is 1 Introduction, 2 Background, 3 Design and implementation, 4 Development process, 5 Method, 6 Results, 7 Threats to validity, 8 Conclusion, Appendix A; new §4 AC (14 phases, each fact traced or attributed to the lead); Deviations AC moved under §5 as a table, sub-requirements unchanged; S7 platform versions from `results/main/campaign.json`; new Appendix A AC; "No results" AC replaced by a results-bearing-statements AC (AFL-024 and AFL-025 drafted together, one commit); section references updated in Technical notes and Test approach. Also: the paper text extracted for research is not committed; the report cites papers by section/figure and quotes at most short phrases (lead decision, 2026-11-17) (req-engineer)
- 2026-11-17 — lead review of the full draft: approved subject to edits A–G (lead decision, 2026-11-17).
  A: AI-involvement disclosure ("How this work was done", §4.1, plus one sentence in §1). B: the
  phase 7 reason. C: phase 8, first reporter-on probe runs superseded; slowdown nearly unchanged with
  both reporters off. D: phase 9, the toy-1 calibration prediction (AFL-011 item (g)) reported as a
  miss for UNIFORM; §6.1 gives the campaign find rate. E: precision fixes in phases 4, 11 and 13 and
  §7 calibration. F: two upstream-source references. G: verdict lines rejoined in §1 and §6.1
  (orchestrator)
- 2026-11-17 — the source for statements the repo does not otherwise record (lead decision,
  2026-11-17): the lead ("the advisor" in CLAUDE.md §7) is an AI assistant (Claude), to which the
  human delegated the lead role on 2026-11-14; the code, reviews and tests were produced by Claude
  Code subagents; the human made the early scoping and design decisions, ran every commit and push,
  and is responsible for the submission; delegation happened because the human had to move to
  another project, and kept decisions moving while the human kept every commit and push at fixed
  stops (phase 7 reason) (orchestrator)
- 2026-11-17 — upstream-source check (read-only fetch approved by the lead for verification only;
  nothing compiled or run; the fetched copies are not kept): AFLFast `afl-fuzz.c` (commit d1d54ca,
  branch master), function `check_crash_handling()`, macOS branch, and AFL++ `docs/INSTALL.md`
  (commit d798677, branch stable), macOS section. Where the source differed from the lead's
  description, the text follows the source: the `launchctl list` check matches only the per-user
  `com.apple.ReportCrash` agent, not `.Root`; it aborts "by default" (unless
  `AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES` is set); AFL's stated reason is that the reporter delays
  the crash signal so crashes can be misread as timeouts; the printed fix uses legacy
  `launchctl unload -w` on both the agent and `.Root`; AFL++ says the daemon must be turned off and
  points to `afl-system-config`. The slowdown range with the per-user reporter on is 58–77% (AFL-011
  Log: 10.7/18.3, 7.7/12.3, 10.8/14.0), not 59–77% (orchestrator)
- 2026-11-17 — AI reviewer pass on the changed text only (lead decision, 2026-11-17); fixes applied:
  phase 13 (the analysis accepted truncated trials, rc 0), phase 4 (CLI module), phase 8 (only the
  official run's D_max counts; slowdown cause worded as PRD §8 words it; per-user vs both reporters),
  §6.1 duplicate sentence removed, "the lead" defined against CLAUDE.md §7 and the crew-lead role,
  §4.1 "key rules" (orchestrator)
- 2026-11-17 — freeze re-check (tester) against PRD §8 at the freeze commit `ff19bef7abb57b1ccbffd0318e2bbcb3c13f9cfc` (`git show ff19bef:docs/PRD.md`; docs/PRD.md is unchanged from ff19bef to HEAD): the §5.3 deviations table maps ten of ten, one to one, (i)–(viii) by numeral and the seed-selection and deterministic-stage deviations by name; (viii) is framed as a deviation from the paper's eq. 4; no contradiction in the table or in the deviation mentions in §2, §3, §4 or §7. AC walk: every AC PASS. The one §5 results-bearing sentence it found ("no sentinel and no unknown bucket") was removed, since §6 states it (orchestrator)
- 2026-11-17 — DoD verified; closed via the gated mv (orchestrator)
