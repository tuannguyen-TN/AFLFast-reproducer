"""AFL-030 (option A): strict static source check over every targets/*.c.

No target may contain a form that ends a run without an ASan report, because
such a crash gets the stackless sentinel "no_stack" and merges with every other
one (ADR-0003, FR-6). The glob runs at test time, so new targets are covered.
This is the single list of banned forms; no other test keeps a copy.
"""
import re
from pathlib import Path

import pytest

TARGETS = Path(__file__).resolve().parent.parent / "targets"
BANNED = [r"\babort\s*\(", r"\braise\s*\(", r"\bkill\s*\(", r"\bsignal\s*\(", r"\bsigaction\b",
          r"\bpthread_kill\b", r"\bassert\s*\(", r"\b__builtin_trap\b",
          r"\b__builtin_unreachable\b", r"\b__builtin_abort\b", r"\b__builtin_debugtrap\b",
          r"\b__builtin_verbose_trap\b", r"\basm\b", r"\b__asm__\b", r"\balarm\s*\(",
          r"\bsetitimer\s*\(", r"\bsetrlimit\s*\(", r"\bkillpg\s*\(",
          r"\b__asm\b", r"\bualarm\s*\(", r"\bsyscall\s*\("]
SOURCES = sorted(TARGETS.glob("*.c"))


_TOKEN = re.compile(r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|/\*.*?\*/|//[^\n]*', re.DOTALL)


def _strip_comments(src: str) -> str:
    """One tokenising pass: keep string/char literals, replace each comment with a space."""
    return _TOKEN.sub(lambda m: m.group() if m.group()[0] in "\"'" else " ", src)


def banned_forms(src: str) -> list[str]:
    """Return the BANNED patterns found in `src` after stripping C comments."""
    code = _strip_comments(src)
    return [p for p in BANNED if re.search(p, code)]


def test_glob_finds_campaign_targets() -> None:
    names = {p.name for p in SOURCES}
    assert {"toy_parser.c", "tlv_parser.c", "mini_format.c"} <= names


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_target_has_no_banned_form(path: Path) -> None:
    assert banned_forms(path.read_text()) == [], path.name


@pytest.mark.parametrize("inject", ["abort();", "assert(0);", "__builtin_trap();"])
@pytest.mark.parametrize("name", ["toy_parser.c", "tlv_parser.c", "mini_format.c"])
def test_injected_form_fails(tmp_path: Path, name: str, inject: str) -> None:
    copy = tmp_path / name
    copy.write_text((TARGETS / name).read_text() + f"\nstatic void x(void) {{ {inject} }}\n")
    assert banned_forms(copy.read_text()), inject


def test_static_assert_and_comments_do_not_fail() -> None:
    assert banned_forms('static_assert(1, "x");\n// abort(); signal\n/* raise(1) */') == []


@pytest.mark.parametrize("src", [
    "return/* c */abort();",
    'puts("//"); abort();',
    'puts("/*"); abort(); /* x */',
])
def test_comment_stripping_bypasses_are_flagged(src: str) -> None:
    assert banned_forms(src) == [r"\babort\s*\("]


@pytest.mark.parametrize("src, pattern", [
    ('__asm("nop");', r"\b__asm\b"),
    ("ualarm(1, 0);", r"\bualarm\s*\("),
    ("syscall (60, 1);", r"\bsyscall\s*\("),
])
def test_new_banned_forms_are_flagged(src: str, pattern: str) -> None:
    assert banned_forms(src) == [pattern]


@pytest.mark.parametrize("src", [
    "int my_syscall_count = 0; int ualarm_ms = 1; int __asm_x;",
    "// __asm(1); ualarm(1,0); syscall(1)\n/* syscall(2) */",
])
def test_new_forms_near_misses_do_not_fail(src: str) -> None:
    assert banned_forms(src) == []


def test_new_forms_inside_string_literals_are_flagged_like_old_forms() -> None:
    assert len(banned_forms('puts("syscall(1) ualarm(1) __asm abort()");')) == 4
