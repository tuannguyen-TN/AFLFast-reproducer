#!/usr/bin/env python3
"""PreToolUse(Bash) gate for git write policy (AFL-015, CLAUDE.md section 7).

- any git push, in any form: exit 2 (agents never push; the human pushes)
- git commit / rm / reset / restore / checkout / config, -c / --config-env, GIT_CONFIG_*:
  exit 2 as well (human decision 2026-11-13: in auto mode an "ask" is settled without a
  human, so only a deny holds in every mode). The human runs these in their own terminal;
  the ticket-id rule for commits lives in the tracked .githooks/commit-msg.
- everything else, and malformed stdin: exit 0 silently

One regex over the whole command text: `git`, optional global options, then the
subcommand. It sees through compound commands, VAR=x prefixes, absolute git
paths, `sh -c "..."`, eval and $(...). Known limits (pushes run indirectly from
scripts, aliases, make) are listed in the AFL-015 ticket log."""
import sys, json, re

# `git` not glued to a word or option char, then global options (-C path, -c k=v, --x[=y]).
# ARG: one shell word, allowing backslash escapes, $'..', and quotes inside the token.
ARG = r"""(?:\\.|\$'(?:\\.|[^'\\])*'|'[^']*'|"(?:\\.|[^"\\])*"|\$\((?:[^()]|\([^()]*\))*\)|\$\{[^}]*\}|`(?:\\.|[^`\\])*`|\$(?![('{])|[^\s\\'"$`])+"""
SPACE_OPT = r"(?:git-dir|work-tree|namespace|super-prefix|config-env)"
# The bare-flag branch excludes the space-form options, so each option token has one parse
# (otherwise a run of `-C` flags backtracks exponentially).
PREFIX = rf"(?<![\w-])git(?:\s+(?:(?:-[Cc]|--{SPACE_OPT})\s+{ARG}|-(?![Cc]\s|-{SPACE_OPT}\s){ARG}))*\s+"
PUSH = re.compile(PREFIX + r"push\b")
ASK = re.compile(PREFIX + r"(?:commit|rm|reset|restore|checkout|config)\b")
# -c / --config-env before the subcommand (inline alias or config injection): always deny.
CFG = re.compile(
    r"(?<![\w-])git(?:\s+(?:(?:-C|--" + SPACE_OPT + r")\s+" + ARG + r"|-(?!c|C\s|-" + SPACE_OPT + r"\s|-config-env)" + ARG + r"))*\s+(?:-c|--config-env)"
)
# Config injected through the environment (inline alias with no -c): always deny.
ENVCFG = re.compile(r"\bGIT_CONFIG_(?:COUNT|PARAMETERS|KEY_\d+|VALUE_\d+|GLOBAL|SYSTEM)\b")
DENY_MSG = (
    "Blocked by git policy hook: the human runs this git command in their own terminal "
    "(CLAUDE.md section 7). For a commit, the orchestrator writes the message to a file "
    "and the human runs `git commit -F <file>`.\n"
)

try:
    data = json.load(sys.stdin)
    cmd = (data.get("tool_input") or {}).get("command", "") or ""
except Exception:
    sys.exit(0)  # never break the session on a parse hiccup
if not isinstance(cmd, str):
    sys.exit(0)
cmd = re.sub(r"\\\n", "", cmd)  # bash deletes backslash-newline, even mid-word (F7)

if PUSH.search(cmd):
    sys.stderr.write(
        "Blocked by git policy hook: agents never run git push; the human pushes "
        "(CLAUDE.md section 7, Push policy).\n"
    )
    sys.exit(2)
if ASK.search(cmd) or CFG.search(cmd) or ENVCFG.search(cmd):
    sys.stderr.write(DENY_MSG)
    sys.exit(2)
sys.exit(0)
