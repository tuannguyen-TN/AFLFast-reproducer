#!/usr/bin/env python3
"""PreToolUse(Bash) gate: block `git commit -m ...` whose message lacks an
AFL-NNN ticket id. Enforces the Definition of Done (every commit traces to a
ticket). Editor commits (no -m) are not inspected and pass through."""
import sys, json, re
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)  # never break the session on a parse hiccup
cmd = (data.get("tool_input") or {}).get("command", "") or ""
if re.search(r"\bgit\s+commit\b", cmd) and re.search(r"-m\b", cmd):
    if not re.search(r"AFL-\d{3}", cmd):
        sys.stderr.write(
            "Blocked by DoD hook: the commit message must reference a ticket id "
            '(e.g. AFL-005). Re-run as: git commit -m "AFL-00X: <what changed>".\n'
        )
        sys.exit(2)  # exit 2 => deny the tool call, feed stderr back to Claude
sys.exit(0)
