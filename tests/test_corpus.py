"""Tests for FR-3 / AFL-004 (corpus retention, f(i), s(i), selection, persistence)."""
import ast
import signal
from pathlib import Path

import pytest

from fuzzer import corpus as corpus_mod
from fuzzer.corpus import Corpus
from fuzzer.executor import ExecResult


def clean(edges: set[int], t: float = 0.01) -> ExecResult:
    return ExecResult(0, None, False, frozenset(edges), t, b"")


CRASH = ExecResult(None, signal.SIGSEGV, False, frozenset({1}), 0.01, b"")
ABORT = ExecResult(None, signal.SIGABRT, False, frozenset({1}), 0.01, b"")  # ASan abort_on_error=1
HANG = ExecResult(None, None, True, frozenset(), 1.0, b"")


def test_retain_iff_new_edge(tmp_path: Path) -> None:
    c = Corpus(tmp_path)
    assert c.observe(b"a", clean({1, 2})) is not None
    assert c.observe(b"b", clean({1})) is None  # subset: no new edge
    assert c.observe(b"c", clean({1, 3})) is not None
    assert [s.data for s in c.seeds] == [b"a", b"c"]


def test_metadata_and_exec_time_from_retaining_run(tmp_path: Path) -> None:
    c = Corpus(tmp_path)
    s = c.observe(b"abc", clean({1, 2}, t=0.5))
    assert s is not None
    c.observe(b"x", clean({1, 2}, t=9.0))  # same path, not retained
    assert (s.id, s.size, s.exec_time, s.times_selected) == (0, 3, 0.5, 0)
    assert s.edges == frozenset({1, 2})


def test_path_freq_counts_non_retained_clean_exec(tmp_path: Path) -> None:
    c = Corpus(tmp_path)
    s = c.observe(b"a", clean({1, 2}))
    assert s is not None and s.path_freq == 1
    assert c.observe(b"b", clean({1, 2})) is None
    assert s.path_freq == 2
    other = c.observe(b"c", clean({3}))
    assert other is not None and other.path_freq == 1 and s.path_freq == 2


@pytest.mark.parametrize(
    ("bad", "outcome"), [(CRASH, "crash"), (ABORT, "crash"), (HANG, "hang")], ids=["sigsegv", "sigabrt", "hang"]
)
def test_non_clean_raises_and_changes_nothing(tmp_path: Path, bad: ExecResult, outcome: str) -> None:
    assert bad.outcome == outcome  # fixture really is the non-clean kind we think it is
    c = Corpus(tmp_path)
    s = c.observe(b"a", clean({1}))
    assert s is not None
    with pytest.raises(ValueError):
        c.observe(b"z", bad)
    with pytest.raises(ValueError):
        c.observe(b"z", ExecResult(None, 11, False, frozenset({1}), 0.0, b""))
    assert c.seeds == [s] and c.seen == {1} and s.path_freq == 1
    assert sum(c._path_count.values()) == 1


def test_round_robin_and_new_seed_joins_cycle(tmp_path: Path) -> None:
    c = Corpus(tmp_path)
    a = c.observe(b"a", clean({1}))
    b = c.observe(b"b", clean({2}))
    assert [c.select(), c.select(), c.select()] == [a, b, a]
    cc = c.observe(b"c", clean({3}))
    assert [c.select(), c.select(), c.select()] == [b, cc, a]


def test_select_empty_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        Corpus(tmp_path).select()


def test_times_selected_only_via_mark_fuzzed(tmp_path: Path) -> None:
    c = Corpus(tmp_path)
    s = c.observe(b"a", clean({1}))
    assert s is not None
    c.select()
    c.observe(b"b", clean({1}))
    assert s.times_selected == 0
    c.mark_fuzzed(s)
    assert s.times_selected == 1


def test_zero_edge_clean_exec_not_retained(tmp_path: Path) -> None:
    c = Corpus(tmp_path)
    assert c.observe(b"a", clean(set())) is None
    assert c.seeds == []


def test_persisted_exact_bytes(tmp_path: Path) -> None:
    c = Corpus(tmp_path)
    c.observe(b"\x00\xffA", clean({1}))
    c.observe(b"", clean({2}))
    assert (tmp_path / "queue" / "id_000000").read_bytes() == b"\x00\xffA"
    assert (tmp_path / "queue" / "id_000001").read_bytes() == b""


def test_corpus_does_not_import_schedule() -> None:
    tree = ast.parse(Path(corpus_mod.__file__).read_text())
    names = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    names |= {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert not any("schedule" in m for m in names)
