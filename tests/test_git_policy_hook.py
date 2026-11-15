"""Offline tests for .claude/hooks/git_policy.py (AFL-015 git-write-policy AC).

The hook verdict is computed from the command text, so no git command runs."""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent / ".claude" / "hooks"


def run(script: str, stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOKS / script)], input=stdin, capture_output=True, text=True, check=False
    )


def payload(cmd: str) -> str:
    return json.dumps({"tool_input": {"command": cmd}})


PUSH_WORD = "pu" + "sh"  # built at runtime: the hook over-blocks text containing it

BLOCKED = [
    "git push",
    "git push --dry-run /nonexistent HEAD",
    "cd /x && git push",
    "true; git push",
    "GIT_DIR=x git push",
    "command git push",
    "git -C . push origin main",
    "git -c push.default=current push",
    "git --no-pager push",
    "git --git-dir=.git push",
    "git --work-tree x push",
    "git --git-dir /tmp/r push",
    "/usr/bin/git push",
    'sh -c "git push"',
    "bash -c 'git push origin main'",
    'eval "git push"',
    "echo $(git push)",
]
BLOCKED += [
    "git -c k=v " + PUSH_WORD,
    "git -C a\\ b " + PUSH_WORD,
    "git \\\n " + PUSH_WORD,
    "git --super-prefix x " + PUSH_WORD,
    "git --config-env k=E " + PUSH_WORD,
    # F5: escaped quotes inside quoted tokens, quoted option value with a space
    "git -C $'a\\'b' " + PUSH_WORD,
    'git -C "a\\"b" ' + PUSH_WORD,
    'git --git-dir="a b" ' + PUSH_WORD,
]
DENIED = [
    'git commit -m "AFL-015: x"',
    "git rm --cached .DS_Store",
    "git reset HEAD f",
    "git restore f",
    "git checkout -- f",
    "git -C . commit -m x",
    "cd x && git commit -m x",
    "git config alias.p push",
    "git -C x config --get user.name",
    "git -c k=v status",
    "git -ck=v status",
    "git --config-env=k=ENV status",
    "git --config-env k=ENV status",
    "git -C dir -c k=v status",
    "true && git -c k=v status",
    "FOO=1 git -c k=v status",
    "git -c alias.p=" + PUSH_WORD + " p",
    # F1: shell-quoting and continuation forms of the global options
    "git -C a\\ b -c k=v status",
    "git -C $'a b' -c k=v status",
    'git -C a"b c" -c k=v status',
    "git \\\n -c k=v status",
    "git -C d \\\n -c k=v status",
    "git --super-prefix x -c k=v status",
    # F5: escaped quotes inside quoted tokens, quoted option value with a space
    "git -C $'a\\'b' -c k=v log",
    'git -C "a\\"b" -c k=v log',
    'git --exec-path="a b" -c k=v log',
    'git -C "a\\"b" commit -m x',
    # F2: config injected through the environment
    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p GIT_CONFIG_VALUE_0=" + PUSH_WORD + " git p",
    "GIT_CONFIG_PARAMETERS=\"'alias.p'='" + PUSH_WORD + "'\" git p",
    "GIT_CONFIG_GLOBAL=/tmp/x git status",
]
# F6: unquoted substitution with a space as an option argument; F7: mid-word continuation
SUBST = ["$(git rev-parse --show-toplevel)", "`git rev-parse --show-toplevel`", "${X:-a b}", "$(echo $(pwd) x)"]
BLOCKED += [f"git -C {s} {PUSH_WORD}" for s in SUBST]
BLOCKED += ["git " + PUSH_WORD[:2] + "\\\n" + PUSH_WORD[2:]]
DENIED += [f"git -C {s} commit -m x" for s in SUBST]
DENIED += [f"git -C {s} -c k=v log" for s in SUBST]
DENIED += ["git com\\\nmit -m x", "git -C a\\\nb -c k=v log"]
PASSED = [
    "git -C $(git rev-parse --show-toplevel) log",
    'git -C "$(pwd)" status',
    'git log --grep="a b"',
    "git status -sb",
    "git diff --staged",
    "git log --oneline -3",
    "git show HEAD",
    "git ls-files .claude",
    "grep -n push x",
    "echo push",
    "git add -p push.md",
    "cat CLAUDE.md",
    "git -C dir log",
    "git log -c",
    "git grep -c x",
    "git log --oneline -1",
]


@pytest.mark.parametrize("cmd", BLOCKED)
def test_push_blocked(cmd: str) -> None:
    r = run("git_policy.py", payload(cmd))
    assert r.returncode == 2
    assert "git push" in r.stderr


@pytest.mark.parametrize("cmd", DENIED)
def test_write_denied(cmd: str) -> None:
    """F4: deny (exit 2), not ask: an ask is settled without a human in auto mode."""
    r = run("git_policy.py", payload(cmd))
    assert r.returncode == 2
    assert r.stdout == ""
    assert "the human runs this git command in their own terminal" in r.stderr
    assert "commit -F <file>" in r.stderr


@pytest.mark.parametrize("cmd", PASSED)
def test_read_only_passes(cmd: str) -> None:
    r = run("git_policy.py", payload(cmd))
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


@pytest.mark.parametrize("stdin", ["", "not json", "[]", '{"tool_input": null}'])
def test_malformed_stdin_passes(stdin: str) -> None:
    r = run("git_policy.py", stdin)
    assert (r.returncode, r.stdout) == (0, "")


HOSTILE = [
    "git -C " + "$''" * 22 + " log",
    "git -C " + "$''" * 100 + " log",
    "git -C " + "$''" * 3334 + " log",  # about 10k characters in one token
    "git " + "-C " * 32 + "log",
    "git " + "-C " * 300 + "log",
    "git " + "--git-dir " * 300 + "log",
    "git -C " + "$'\\'" * 2500 + " log",  # F5 branches: ANSI-C quote with escape
    "git -C " + '"\\"' * 3334 + " log",  # F5 branches: double quote with escape
    "git -C " + "$'\\'" * 40 + " log",
    "git -C " + '"\\"' * 40 + " log",
    "git -C " + "$(" * 3334 + " log",  # F6 branches: unclosed substitutions
    "git -C " + "`" * 10000 + " log",
    "git -C " + "\\\n" * 5000 + " log",
    "git -C " + "$(a (b" * 1500 + " log",
    "git -C " + "${" * 5000 + " log",
    "git -C " + "$(a)" * 2500 + " log",  # guards the `$(?![('{])` exclusion (R3)
    "git -C " + "${a}" * 2500 + " log",
    "git -C " + "$(a)" * 40 + " log",
]


@pytest.mark.parametrize("cmd", HOSTILE, ids=lambda c: f"{len(c)}chars")
def test_hostile_input_finishes_fast(cmd: str) -> None:
    """Regression: exponential regex backtracking on `$''` runs and repeated bare options
    (AFL-015 review bounce 2). The hook must verdict in well under a second."""
    t0 = time.monotonic()
    try:
        r = subprocess.run(
            [sys.executable, str(HOOKS / "git_policy.py")],
            input=payload(cmd), capture_output=True, text=True, check=False, timeout=10,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("hook did not finish within 10 s (regex backtracking)")
    assert time.monotonic() - t0 < 1.0
    assert r.returncode == 0


def test_ticket_id_hook_unchanged() -> None:
    """AC test (d): require_ticket_in_commit.py behaves as before."""
    assert run("require_ticket_in_commit.py", payload('git commit -m "no id"')).returncode == 2
    assert run("require_ticket_in_commit.py", payload('git commit -m "AFL-015: x"')).returncode == 0
