# AFLFast Reproducer

A naive coverage-guided greybox fuzzer (AFL-style) that **reproduces AFLFast's
power-schedule advantage** under the **evaluation methodology of Klees et al.**

- **What it reproduces:** AFLFast (CCS 2016) — energy spent on rare-path seeds
  beats uniform energy allocation.
- **How it measures it:** _Evaluating Fuzz Testing_ (CCS 2018) — repeated trials,
  Mann-Whitney U significance, A12 effect size, honest crash de-duplication.

See **`docs/PRD.md`** for full requirements and **`CLAUDE.md`** for the repo map,
commands, and working agreement. The development process (roles, tickets, SDLC)
lives in **`.claude/agents/`** and **`tickets/`**.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
make -C targets   # needs Homebrew LLVM, see note below
python harness/run_campaign.py experiments/configs/main.yaml
python harness/aggregate.py results/ && python harness/plots.py results/
```

> Requires Homebrew LLVM (`brew install llvm`): Apple clang's ASan hangs on macOS 26.x. See ADR-0001.

## Papers (download locally into `docs/papers/`)

- `aflfast-ccs2016-coverage-based-greybox-fuzzing-as-markov-chain.pdf`
- `klees-ccs2018-evaluating-fuzz-testing.pdf`

## Scope & ethics

Fuzzing runs only against the in-repo targets we own, entirely locally. This is a
methodology reproduction, not an offensive-security tool.
