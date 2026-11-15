#!/usr/bin/env python3
"""PreToolUse(Bash) gate: block moving a ticket into tickets/done/ unless the
quality gates pass. Ties the Definition of Done to deterministic checks so
nothing closes red. Tools that aren't installed yet are skipped (so an early
scaffolding ticket can close before the toolchain exists); once installed, they
are enforced."""
import sys, json, re, os, subprocess, shutil
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
cmd = (data.get("tool_input") or {}).get("command", "") or ""
if not (re.search(r"\bmv\b", cmd) and re.search(r"tickets/done/", cmd)):
    sys.exit(0)

os.chdir(os.environ.get("CLAUDE_PROJECT_DIR", "."))
venv = os.path.join(os.getcwd(), ".venv", "bin")
if os.path.isdir(venv):  # prefer the project venv over whatever python3 runs the hook
    os.environ["PATH"] = venv + os.pathsep + os.environ.get("PATH", "")
py = shutil.which("python") or sys.executable

checks = []
if shutil.which("ruff"):
    checks.append(["ruff", "check", "."])
if shutil.which("mypy"):
    checks.append(["mypy", "src"])
if subprocess.run([py, "-c", "import pytest"], capture_output=True).returncode == 0:
    checks.append([py, "-m", "pytest", "-q"])

for c in checks:
    r = subprocess.run(c, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        tail = (r.stdout + r.stderr)[-800:]
        sys.stderr.write(
            f"Blocked by DoD hook: `{' '.join(c)}` failed, so this ticket cannot "
            f"move to done/. Fix it first.\n--- output tail ---\n{tail}\n"
        )
        sys.exit(2)
sys.exit(0)
