"""AFL-013: crash de-duplication (harness/dedup.py) and ADR-0003."""
import csv
import json
import re
import sys
from pathlib import Path

import pytest
from conftest import needs_clang

from fuzzer.executor import Executor
from fuzzer.fuzzer import CRASH_COLUMNS, FuzzConfig, crash_site, run

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import dedup
from dedup import bucket_trial


def trial(tmp_path: Path, rows: list[tuple[float, int, int, str, str]]) -> Path:
    """rows: (elapsed_s, execs, signal, crash_site, saved)."""
    with (tmp_path / "crash_events.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(CRASH_COLUMNS)
        for e, x, sig, site, saved in rows:
            w.writerow([e, x, sig, site, 1, saved])
    return tmp_path


def test_every_event_counted_only_one_saved(tmp_path: Path) -> None:
    rows = [(0.1 * i, i, 6, "scan", "crashes/000000.bin" if i == 3 else "") for i in range(1, 8)]
    (b,) = bucket_trial(trial(tmp_path, rows), "toy_parser")
    assert b.count == 7 and b.example == Path("crashes/000000.bin")
    assert (b.first_elapsed_s, b.first_execs) == (0.1, 1)


def test_signal_not_in_key(tmp_path: Path) -> None:
    (b,) = bucket_trial(trial(tmp_path, [(1, 1, 6, "scan", ""), (2, 2, 11, "scan", "")]),
                         "toy_parser")
    assert b.count == 2 and b.key == "scan" and b.example is None


def test_different_sites_different_buckets_sorted_and_mapped(tmp_path: Path) -> None:
    bs = bucket_trial(trial(tmp_path, [(2, 2, 6, "check", "a"), (1, 1, 6, "scan", "b")]),
                      target="toy_parser")
    assert [(b.key, b.bug_id) for b in bs] == [("scan", "toy-2"), ("check", "toy-1")]
    assert len(bs) == 2


def test_unmatched_real_site_is_unknown(tmp_path: Path) -> None:
    (b,) = bucket_trial(trial(tmp_path, [(1, 1, 6, "main", "a")]), target="toy_parser")
    assert b.bug_id is None


def test_bug_id_is_per_target_and_unknown_target_raises(tmp_path: Path) -> None:
    t = trial(tmp_path, [(1, 1, 6, "main", "a")])
    assert bucket_trial(t, "tlv_parser")[0].bug_id == "tlv-1"
    assert bucket_trial(t, "toy_parser")[0].bug_id is None
    with pytest.raises(ValueError, match="nope"):
        bucket_trial(t, "nope")


def test_sentinels_never_merged(tmp_path: Path) -> None:
    sent = ["no_stack", "unsymbolized", "no_target_frame"]
    rows = [(1, 1, 6, "scan", "a")] + [(2 + i, 2 + i, 6, s, "") for i, s in enumerate(sent)]
    bs = bucket_trial(trial(tmp_path, rows), target="toy_parser")
    assert [b.key for b in bs] == ["scan", *sent]
    assert [b.bug_id for b in bs] == ["toy-2", None, None, None]


def test_sentinel_named_like_function_still_unknown(tmp_path: Path) -> None:
    gt = tmp_path / "gt.json"
    gt.write_text('{"x": {"target": "t", "function": "unsymbolized", "file": "t.c"}}')
    (b,) = bucket_trial(trial(tmp_path, [(1, 1, 6, "unsymbolized", "")]), "t", ground_truth=gt)
    assert b.bug_id is None


def test_key_is_shared_extractor_output(tmp_path: Path) -> None:
    report = (ROOT / "tests/fixtures/tlv_parser_asan_memcpy.txt").read_bytes()
    site = crash_site(report, "tlv_parser.c")
    assert site == "main"
    (b,) = bucket_trial(trial(tmp_path, [(1, 1, 6, site, "a")]), "tlv_parser")
    assert b.key == site


def test_no_frame_parsing_and_docstring_statements() -> None:
    src = Path(dedup.__file__).read_text()
    assert not re.search(r"#\\d\+|0x\[", src) and "ASan frame" not in src.split('"""')[2]
    doc = dedup.__doc__ or ""
    assert "Two bugs in one function" in doc and "own function" in doc
    assert "first in-target stack frame" in doc and "overcount" in doc


def test_adr_0003_content() -> None:
    adr = (ROOT / "docs/adr/0003-crash-site-dedup.md").read_text()
    for s in ("first in-target stack frame", "site only", "no_target_frame", "process-invariant"):
        assert s in adr


@needs_clang
def test_real_tlv_run_every_real_bucket_has_example(tmp_path: Path) -> None:
    seeds = tmp_path / "seeds"
    seeds.mkdir()
    (seeds / "S0").write_bytes(bytes([65, 60]) + b"x" * 60)
    out = tmp_path / "out"
    run(FuzzConfig(ROOT / "targets/bin/tlv_parser", "uniform", 60, 1, out, seeds, max_execs=3000))
    bs = bucket_trial(out, "tlv_parser")
    assert bs
    for b in bs:
        if b.key not in dedup.SENTINELS:
            assert b.example is not None and (out / b.example).is_file()


@needs_clang
def test_crash_site_process_invariant() -> None:
    ex = Executor(ROOT / "targets/bin/toy_parser")
    runs = [ex.run(b"!aaa") for _ in range(2)]
    ex.close()
    sites = [crash_site(r.stderr, "toy_parser.c") for r in runs]
    truth = json.loads((ROOT / "targets/ground_truth.json").read_text())
    assert sites[0] == sites[1] == truth["toy-2"]["function"]
    for s, r in zip(sites, runs, strict=True):
        m = re.search(rb"==(\d+)==", r.stderr)
        assert m is not None
        assert "0x" not in s and "/" not in s and m.group(1).decode() not in s
