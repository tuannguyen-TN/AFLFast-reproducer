"""AFL-037 AC 6 (closes the AFL-007 gap): the ASan fixture is pinned to the source it was
captured from, so a targets/tlv_parser.c edit without re-capturing breaks a test."""
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_fixture_header_sha_matches_tlv_parser_source() -> None:
    header = (ROOT / "tests/fixtures/tlv_parser_asan_memcpy.txt").read_text().splitlines()[0]
    m = re.search(r"sha256 ([0-9a-f]{64})\s*$", header)
    assert m, header
    assert m.group(1) == hashlib.sha256((ROOT / "targets/tlv_parser.c").read_bytes()).hexdigest()
