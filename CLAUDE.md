# CLAUDE.md — Project Operating Manual

> Entry point for Claude (and humans) working in this repo. Read this first,
> then the role file for whatever hat you are wearing (`.claude/agents/`), then the
> ticket you are working (`tickets/`).

## 1. What this project is

A **naive coverage-guided greybox fuzzer** (AFL-style) built from scratch in
Python + C, used to **reproduce the central result of AFLFast** — that a
rare-path *power schedule* beats uniform energy allocation — **evaluated under
the methodology of Klees et al.** (repeated trials, statistical significance,
honest crash de-duplication).

One-sentence scope: *reproduce the direction of AFLFast's power-schedule
advantage at small scale, measured the way "Evaluating Fuzz Testing" requires.*

The two source papers (download into `docs/papers/`, names must match):
- `aflfast-ccs2016-coverage-based-greybox-fuzzing-as-markov-chain.pdf`
  — Böhme, Pham, Roychoudhury, *Coverage-based Greybox Fuzzing as Markov Chain*, CCS 2016. **The result we reproduce.**
- `klees-ccs2018-evaluating-fuzz-testing.pdf`
  — Klees, Ruef, Cooper, Wei, Hicks, *Evaluating Fuzz Testing*, CCS 2018. **The evaluation standard we hold ourselves to.**

Full requirements live in `docs/PRD.md`. **The PRD is the source of truth**;
if code and PRD disagree, the PRD wins (or the PRD gets a ticket to change).

## 2. Mental model (do not get this wrong)

Coverage feedback does **not** steer mutations. Mutation is *blind*. Coverage
decides only (a) which candidates are **retained** in the corpus and (b) via the
power schedule, **how much energy** each retained seed gets. AFLFast changes
only (b). Keep this distinction crisp in code comments and in the report.

## 3. Directory tree

```
greybox-fuzz-repro/
├── CLAUDE.md                  # this file — project operating manual
├── README.md                  # quickstart for a human
├── pyproject.toml             # tooling config (ruff, mypy, pytest)
├── requirements.txt           # pinned-ish dependencies
├── .gitignore
│
├── docs/
│   ├── PRD.md                 # Product Requirements Document (source of truth)
│   ├── papers/                # the two PDFs (gitignored; download locally)
│   └── adr/                   # Architecture Decision Records (architect owns)
│
├── .claude/                   # Claude Code config (auto-discovered on launch)
│   ├── agents/                # the crew AS subagents — one file per role
│   │   ├── vision.md          # north star / sponsor; guards scope (read-only)
│   │   ├── req-engineer.md    # turns papers+vision into testable requirements
│   │   ├── architect.md       # system design, interfaces, ADRs
│   │   ├── developer.md       # implements tickets + unit tests
│   │   ├── reviewer.md        # code review gate against acceptance criteria
│   │   ├── tester.md          # test strategy + experimental-validity gate
│   │   └── crew-lead.md       # team charter: SDLC, board, DoR/DoD, handoffs
│   └── commands/              # slash commands: /board /groom /next-ticket /review-ticket
│
├── tickets/                   # the ticketing system (see tickets/README.md)
│   ├── README.md              # ticket lifecycle + ID scheme + SDLC mapping
│   ├── templates/
│   │   └── ticket-template.md
│   ├── backlog/               # req-engineer writes here
│   ├── in-progress/           # developer
│   ├── review/                # reviewer
│   ├── testing/               # tester
│   └── done/                  # crew lead verifies DoD, moves here
│
├── src/fuzzer/                # the fuzzer (Python)
│   ├── coverage.py            # FR-1  read instrumented edge bitmap
│   ├── executor.py            # FR-2  run target, timeout, capture signals
│   ├── corpus.py              # FR-3  seed queue, retain-on-new-coverage
│   ├── mutator.py             # FR-4  blind mutation operators + havoc + splice
│   ├── schedule.py            # FR-5  UNIFORM (baseline) vs FAST (AFLFast)
│   ├── fuzzer.py              # FR-*  main loop
│   └── cli.py                 # FR-10 command-line entry point
│
├── targets/                   # C programs under test (with planted bugs)
│   ├── Makefile               # clang + SanitizerCoverage + ASan
│   ├── toy_parser.c           # control target, documented known bugs
│   └── tlv_parser.c           # length-field stack overflow
│
├── harness/                   # experiment + evaluation (the Klees layer)
│   ├── run_campaign.py        # FR-7  N trials x targets x schedules
│   ├── dedup.py               # FR-6  honest crash bucketing
│   ├── aggregate.py           # FR-9  medians, Mann-Whitney U, A12 effect size
│   └── plots.py               # FR-8  coverage/crash-over-time with variance
│
├── experiments/configs/       # YAML experiment definitions
│   └── main.yaml
├── results/                   # generated metrics + figures (gitignored)
└── tests/                     # pytest unit/integration tests
```

## 4. Commands

```bash
# environment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# build instrumented targets (needs Homebrew LLVM: `brew install llvm`;
# Apple clang's ASan hangs on macOS 26.x, see ADR-0001)
make -C targets

# run the fuzzer once
python -m fuzzer.cli --target targets/bin/tlv_parser --schedule fast \
    --seconds 600 --seed 1 --out results/demo

# run the full experiment (all trials/targets/schedules)
python harness/run_campaign.py experiments/configs/main.yaml

# analyse + plot
python harness/aggregate.py results/
python harness/plots.py results/

# quality gates
ruff check . && mypy src && pytest
```

## 5. Working agreement

- **No work without a ticket.** Every change traces to a ticket ID (e.g. `AFL-005`).
- **Ethics / scope guardrail:** fuzz **only** the targets in `targets/` (code we
  own). No network, no third-party or remote services, all runs local. This is a
  security *methodology* project, not an offensive one.
- **Reproducibility is a requirement, not a nicety:** every trial uses an explicit
  RNG seed; pin dependencies; record the exact commit + command for every result.
- **Honesty over hype:** a null result, reported with Klees-compliant statistics,
  is a passing outcome. Overclaiming is a failing one.

## 6. Where to look next

| If you are the… | Read |
|---|---|
| sponsor / deciding scope | `.claude/agents/vision.md`, `docs/PRD.md §2–3` |
| requirements engineer | `.claude/agents/req-engineer.md`, `docs/PRD.md §6–7` |
| architect | `.claude/agents/architect.md`, `docs/adr/` |
| developer | `.claude/agents/developer.md`, your ticket, `docs/PRD.md §6` |
| reviewer | `.claude/agents/reviewer.md`, ticket acceptance criteria |
| tester | `.claude/agents/tester.md`, `docs/PRD.md §8` (experimental design) |
| anyone, on process | `.claude/agents/crew-lead.md`, `tickets/README.md` |

## 7. Orchestration (running the crew)

This session is the **orchestrator**. In standard Claude Code the main session is
the orchestrator: it delegates stage by stage to the subagents in
`.claude/agents/` (hierarchical, orchestrator-led), each working in its own
context with its own tool scope, and synthesises the results here. Use subagents,
not Agent Teams — teams are peer-to-peer with no orchestrator, which is the
opposite of this crew model.

### Delegation map (one ticket through the SDLC)
| Stage | Subagent | Board move on handoff |
|---|---|---|
| ready check | crew-lead | backlog → (ready) |
| implement | developer | in-progress → review |
| review | reviewer | review → testing (or back) |
| verify | tester | testing → (ready to close) (or back) |
| close | crew-lead | → done |

Drivers: `/next-ticket` (one ticket end to end) and `/run-backlog` (loop over the
whole backlog). Both pause for the human stop conditions below.

### Stop conditions (the orchestrator MUST pause for the human)
1. **AFL-001** — the GO/NO-GO spike: present the two edge sets, wait for a decision.
2. **Any git commit** — show the change, wait for approval; never auto-commit
   (check-in review is where paper-fidelity drift is caught).
3. **A ticket bounces twice** — stop and ask, don't loop.

### Deterministic enforcement (hooks, in `.claude/settings.json`)
A prompt here is ~80% obeyed; a hook is 100%. Two PreToolUse(Bash) hooks enforce
the Definition of Done regardless of what any agent decides:
- `require_ticket_in_commit.py` — blocks a `git commit -m` whose message lacks an
  `AFL-NNN` id.
- `gate_ticket_done.py` — blocks moving a ticket into `tickets/done/` unless
  `ruff`, `mypy`, and `pytest` pass (absent tools are skipped early on).
These are rules, not suggestions: the crew cannot skip them.
