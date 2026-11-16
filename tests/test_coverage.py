"""AFL-002: edge collection, new/not-new reporting, path_id, -O branch distinctness."""
import subprocess
from pathlib import Path

import pytest
from conftest import needs_clang

from fuzzer.corpus import Corpus
from fuzzer.coverage import BUCKET_LUT, Hit, ShmBitmap, has_new_edges, path_id, run_with_coverage
from fuzzer.executor import ExecResult

TARGETS = Path(__file__).resolve().parent.parent / "targets"


def ids(hits: frozenset[Hit]) -> frozenset[int]:
    return frozenset(e for e, _ in hits)  # AFL-002 distinctness is over edge ids


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
    seen: set[Hit] = set()
    assert has_new_edges(a, seen)
    seen |= a
    assert not has_new_edges(a, seen)
    assert has_new_edges(b, seen)


@needs_clang
def test_each_branch_side_distinct_toy(toy: str) -> None:
    ladder = [b"", b"A", b"B", b"BA", b"BU", b"BUA", b"BUG"]  # BUG crashes; edges still recorded
    sets = [ids(run_with_coverage(toy, i)) for i in ladder]
    assert len(set(sets)) == len(sets)


@needs_clang
def test_branch_distinct_tlv(tlv: str) -> None:
    assert ids(run_with_coverage(tlv, b"A")) != ids(run_with_coverage(tlv, b"AA"))


def h(*edges: int) -> frozenset[Hit]:
    return frozenset((e, 1) for e in edges)


def test_path_id_stable_and_distinct() -> None:
    assert path_id(h(1, 2, 3)) == path_id(h(3, 2, 1))
    assert path_id(h(1, 2, 3)) != path_id(h(1, 2))
    assert path_id(h(1, 2, 3)) == 7768930058469586361  # fixed value: not process-salted
    assert path_id(frozenset({(1, 1)})) != path_id(frozenset({(1, 2)}))  # bucket is in the id


BUCKETS = {0: 0, 1: 1, 2: 2, 3: 4, 4: 8, 7: 8, 8: 16, 15: 16, 16: 32, 31: 32,
           32: 64, 127: 64, 128: 128, 255: 128}


@pytest.mark.parametrize(("count", "bucket"), BUCKETS.items())
def test_bucket_boundaries(count: int, bucket: int) -> None:
    assert int(BUCKET_LUT[count]) == bucket
    bm = ShmBitmap()
    try:
        bm._map[5] = count
        assert bm.hits() == (frozenset({(5, bucket)}) if count else frozenset())  # 0: no pair
    finally:
        bm.close()


def result(*hits: Hit) -> ExecResult:
    return ExecResult(0, None, False, frozenset(hits), 0.01, b"")


def test_retained_on_bucket_change_alone_and_edges_unchanged(tmp_path: Path) -> None:
    c = Corpus(tmp_path)
    assert c.observe(b"a", result((1, 1), (2, 1))) is not None
    assert c.observe(b"b", result((1, 1), (2, 1))) is None  # same pairs: not retained
    assert c.observe(b"c", result((1, 1), (2, 8))) is not None  # only edge 2's bucket changed
    assert len(c.seen) == 2  # final_edges is distinct edge ids, not (edge, bucket) pairs
    assert result((1, 1), (2, 8)).edges == result((1, 4), (2, 1)).edges == {1, 2}


@needs_clang
def test_counter_saturates_at_255_real_binary() -> None:
    mini = str(TARGETS / "bin" / "mini_format")
    subprocess.run(["make", "-C", str(TARGETS), "bin/mini_format"], check=True)
    data = b"MF\x01\x00" + b"C\x00" * 500  # the record loop runs 500 times
    bm = ShmBitmap()
    try:
        subprocess.run([mini], input=data, env=bm.env(), check=False, capture_output=True)
        assert int(bm._map.max()) == 255  # saturated, not wrapped (500 % 256 = 244)
        assert (int(bm._map.argmax()), 128) in bm.hits()
    finally:
        bm.close()


def test_cov_rt_saturates_in_source() -> None:
    assert "v + (v != 255)" in (TARGETS / "cov_rt.c").read_text()
