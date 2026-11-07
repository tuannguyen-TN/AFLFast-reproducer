"""AFL-002: edge collection, new/not-new reporting, path_id, -O branch distinctness."""
import shutil
import subprocess
from pathlib import Path

import pytest

from fuzzer.coverage import has_new_edges, path_id, run_with_coverage

TARGETS = Path(__file__).resolve().parent.parent / "targets"
needs_clang = pytest.mark.skipif(shutil.which("clang") is None, reason="clang unavailable")


@pytest.fixture(scope="module")
def toy() -> str:
    subprocess.run(["make", "-C", str(TARGETS), "bin/toy_parser", "bin/tlv_parser"], check=True)
    return str(TARGETS / "bin" / "toy_parser")


@pytest.fixture(scope="module")
def tlv(toy: str) -> str:
    return str(TARGETS / "bin" / "tlv_parser")


@needs_clang
def test_nonempty_repeatable_input_dependent(toy: str) -> None:
    a = run_with_coverage(toy, b"A")
    assert a
    assert a == run_with_coverage(toy, b"A")
    assert a != run_with_coverage(toy, b"B")


@needs_clang
def test_new_vs_seen(toy: str) -> None:
    a, b = run_with_coverage(toy, b"A"), run_with_coverage(toy, b"B")
    seen: set[int] = set()
    assert has_new_edges(a, seen)
    seen |= a
    assert not has_new_edges(a, seen)
    assert has_new_edges(b, seen)


@needs_clang
def test_each_branch_side_distinct_toy(toy: str) -> None:
    ladder = [b"", b"A", b"B", b"BA", b"BU", b"BUA", b"BUG"]  # BUG crashes; edges still recorded
    sets = [run_with_coverage(toy, i) for i in ladder]
    assert len(set(sets)) == len(sets)


@needs_clang
def test_branch_distinct_tlv(tlv: str) -> None:
    assert run_with_coverage(tlv, b"A") != run_with_coverage(tlv, b"AA")


def test_path_id_stable_and_distinct() -> None:
    assert path_id(frozenset({1, 2, 3})) == path_id(frozenset({3, 2, 1}))
    assert path_id(frozenset({1, 2, 3})) != path_id(frozenset({1, 2}))
    assert path_id(frozenset({1, 2, 3})) == 11402386789778234582  # fixed value: not process-salted

