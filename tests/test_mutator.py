"""Tests for FR-4 / AFL-005 (blind havoc+splice mutator, NFR-1 determinism)."""
import ast
import inspect
import random
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pytest

from fuzzer import mutator
from fuzzer.mutator import (
    ARITH_MAX,
    MAX_INPUT,
    arith,
    bit_flip,
    byte_flip,
    delete_bytes,
    havoc,
    insert_bytes,
    interesting,
    mutate,
    splice,
)

SRC = Path(mutator.__file__)
DATA = bytes(range(16))


def rng(seed: int = 1) -> random.Random:
    return random.Random(seed)


def test_bit_flip_changes_exactly_one_bit() -> None:
    for s in range(50):
        out = bit_flip(DATA, rng(s))
        diff = [a ^ b for a, b in zip(DATA, out, strict=True)]
        assert len(out) == len(DATA) and sum(d.bit_count() for d in diff) == 1


def test_byte_flip_inverts_exactly_one_byte() -> None:
    for s in range(50):
        out = byte_flip(DATA, rng(s))
        diff = [a ^ b for a, b in zip(DATA, out, strict=True)]
        assert max(diff) == 0xFF and sum(1 for d in diff if d) == 1


def test_arith_adds_bounded_delta_in_one_window() -> None:
    seen = set()
    for s in range(200):
        out = arith(DATA, rng(s))
        assert len(out) == len(DATA) and out != DATA
        idx = [i for i in range(16) if out[i] != DATA[i]]
        assert idx and idx[-1] - idx[0] < 4
        seen.add(len(idx))
    assert {1, 2} <= seen  # multiple widths used


def test_arith_8bit_delta_range_and_wrap() -> None:
    deltas = set()
    for s in range(500):
        out = arith(b"\x80", rng(s))
        deltas.add((out[0] - 0x80) % 256)
    assert all(d <= ARITH_MAX or d >= 256 - ARITH_MAX for d in deltas) and 0 not in deltas
    assert arith(b"\xff", random.Random(0))[0] != 0xFF


def test_interesting_writes_afl_value() -> None:
    vals8 = {v % 256 for v in mutator.INTERESTING_8}
    for s in range(100):
        assert interesting(b"\x55", rng(s))[0] in vals8
    outs = {interesting(b"\x55" * 8, rng(s)) for s in range(200)}
    assert any(b"\xff\xff\xff\x7f" in o or b"\x7f\xff\xff\xff" in o for o in outs)


def test_insert_grows_and_respects_cap() -> None:
    assert len(insert_bytes(b"", rng())) >= 1
    assert all(len(insert_bytes(b"a" * 5, rng(s))) > 5 for s in range(20))
    assert insert_bytes(b"a" * MAX_INPUT, rng()) == b"a" * MAX_INPUT


def test_delete_shrinks_and_keeps_one_byte() -> None:
    for s in range(50):
        out = delete_bytes(DATA, rng(s))
        assert 1 <= len(out) < len(DATA)
    assert delete_bytes(b"x", rng()) == b"x"


def test_empty_input_only_length_changing_ops() -> None:
    for op in (bit_flip, byte_flip, arith, interesting, delete_bytes):
        assert op(b"", rng()) == b""
    assert insert_bytes(b"", rng()) != b""


def test_havoc_stacks_and_stays_bounded() -> None:
    outs = [havoc(DATA, rng(s)) for s in range(100)]
    assert any(o != DATA for o in outs)
    assert all(len(o) <= MAX_INPUT for o in outs)
    # stack depth 2..128: with >=2 ops on 16 bytes, most outputs differ by >1 bit
    assert sum(o != DATA for o in outs) > 90


def test_splice_one_shared_cut_never_empty() -> None:
    a, b = b"A" * 20, b"B" * 30
    ks = set()
    for s in range(300):
        out = splice(a, b, rng(s))
        k = len(out) - len(out.lstrip(b"A"))
        assert out == a[:k] + b[k:] and 1 <= k < 20 and out
        ks.add(k)
    assert min(ks) == 1 and max(ks) == 19
    assert splice(b"", b, rng()) == b"" and splice(b"x", b, rng()) == b"x"
    assert splice(a, b"y", rng()) == a


def test_mutate_splices_only_with_pool_of_two() -> None:
    a, b = b"A" * 64, b"B" * 64
    def has_b(pool: list[bytes]) -> bool:
        r = rng()
        return any(b"B" * 8 in mutate(a, r, pool) for _ in range(300))
    assert has_b([a, b])
    assert not has_b([a])
    assert not has_b([])


def test_determinism_under_seed() -> None:
    pool = [b"hello world", b"GET /index", b"\x00\x01\x02"]
    def seq(seed: int) -> list[bytes]:
        r = rng(seed)
        return [mutate(b"hello world", r, pool) for _ in range(100)]
    assert seq(7) == seq(7)
    assert seq(7) != seq(8)


def test_imports_stdlib_only() -> None:
    names: set[str] = set()
    for n in ast.walk(ast.parse(SRC.read_text())):
        if isinstance(n, ast.Import):
            names |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            assert n.level == 0
            names.add((n.module or "").split(".")[0])
    assert names <= {"random", "typing", "collections"}
    assert "fuzzer" not in names


_BANNED_NAMES = {
    "secrets", "time", "uuid", "numpy", "os", "__import__", "getattr", "setattr", "eval",
    "exec", "compile", "__builtins__", "globals", "locals", "vars", "importlib", "hash", "id",
}


def test_sole_randomness_source_whole_module() -> None:
    tree = ast.parse(SRC.read_text())
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "random":
            assert n.attr == "Random", f"random.{n.attr} at line {n.lineno}"
        if isinstance(n, ast.Name):
            assert n.id not in _BANNED_NAMES, f"{n.id} at line {n.lineno}"
        if isinstance(n, ast.Import | ast.ImportFrom):
            assert all(a.asname is None for a in n.names), f"import alias at line {n.lineno}"
        if isinstance(n, ast.Import):
            assert not {a.name.split(".")[0] for a in n.names} & _BANNED_NAMES
        if isinstance(n, ast.ImportFrom):
            assert (n.module or "").split(".")[0] not in _BANNED_NAMES
            if n.module == "random":
                assert all(a.name == "Random" for a in n.names)
        if isinstance(n, ast.Call):
            f = n.func
            assert not (isinstance(f, ast.Attribute) and f.attr == "Random"), f"Random() at {n.lineno}"
            assert not (isinstance(f, ast.Name) and f.id == "Random"), f"Random() at {n.lineno}"


def test_public_functions_take_injected_rng() -> None:
    for name in ("bit_flip", "byte_flip", "arith", "interesting", "insert_bytes",
                 "delete_bytes", "havoc", "splice", "mutate"):
        p = inspect.signature(getattr(mutator, name)).parameters
        assert "rng" in p and p["rng"].annotation is random.Random, name


def test_afl_constants_pinned() -> None:
    assert mutator.ARITH_MAX == 35 and mutator.HAVOC_STACK_POW2 == 7
    assert mutator.MAX_INPUT == 1024 and mutator.SPLICE_PROB == 0.1 and mutator._MAX_BLOCK == 32
    assert mutator.INTERESTING_8 == (-128, -1, 0, 1, 16, 32, 64, 100, 127)
    assert mutator.INTERESTING_16 == (-32768, -129, 128, 255, 256, 512, 1000, 1024, 4096, 32767)
    assert mutator.INTERESTING_32 == (-2147483648, -100663046, -32769, 32768, 65535, 65536,
                                      100663045, 2147483647)


def test_interesting_16bit_both_orders_and_includes_8bit() -> None:
    outs = {interesting(b"\x55\x55", rng(s)) for s in range(400)}
    assert b"\xff\x00" in outs and b"\x00\xff" in outs  # 255, LE and BE
    assert b"d\x00" in outs or b"\x00d" in outs  # 8-bit value 100 inside a 16-bit write


def test_havoc_depth_and_op_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: set[str] = set()
    calls: Counter[str] = Counter()

    def wrap(op: Callable[[bytes, random.Random], bytes]) -> Callable[[bytes, random.Random], bytes]:
        def counted(d: bytes, r: random.Random) -> bytes:
            calls[op.__name__] += 1
            return op(d, r)
        return counted

    monkeypatch.setattr(mutator, "_HAVOC_OPS", tuple(wrap(o) for o in mutator._HAVOC_OPS))
    depths = []
    for s in range(1500):
        calls.clear()
        havoc(DATA, rng(s))
        depths.append(sum(calls.values()))
        seen.update(calls)
    assert min(depths) == 2 and max(depths) == 128 and set(depths) <= {1 << i for i in range(1, 8)}
    assert seen == {"bit_flip", "byte_flip", "arith", "interesting", "insert_bytes", "delete_bytes"}


def test_mutate_truncates_to_max_input() -> None:
    big = b"a" * 2000
    for pool in ([], [big, b"b" * 2000]):
        for s in range(30):
            assert len(mutate(big, rng(s), pool)) <= MAX_INPUT


def test_bit_flip_reaches_all_eight_positions() -> None:
    assert {bit_flip(b"\x00", rng(s))[0] for s in range(300)} == {1 << i for i in range(8)}


def test_insert_reaches_both_ends() -> None:
    outs = [insert_bytes(b"abcd", rng(s)) for s in range(400)]
    assert any(o.startswith(b"abcd") and len(o) > 4 for o in outs)  # pos == len(data)
    assert any(o.endswith(b"abcd") and len(o) > 4 for o in outs)  # pos == 0


def test_insert_blocks_not_constant() -> None:
    blocks = [insert_bytes(b"", rng(s)) for s in range(200)]
    assert any(len(b) >= 2 and len(set(b)) > 1 for b in blocks)


def test_delete_reaches_tail_and_head() -> None:
    outs = [delete_bytes(DATA, rng(s)) for s in range(400)]
    assert any(DATA.startswith(o) for o in outs)  # last byte removed
    assert any(DATA.endswith(o) for o in outs)  # first byte removed


def test_interesting_32bit_includes_8_and_16bit_values() -> None:
    outs = {interesting(b"\x55" * 4, rng(s)) for s in range(800)}
    assert {b"\x80\xff\xff\xff", b"\xff\xff\xff\x80"} & outs  # -128 as 32-bit
    assert {b"\x00\x01\x00\x00", b"\x00\x00\x01\x00"} & outs  # 256 as 32-bit
    assert {b"\xff\xff\xff\x7f", b"\x7f\xff\xff\xff"} & outs  # a 32-bit-only value


def test_arith_both_delta_signs() -> None:
    d = {(arith(b"\x80", rng(s))[0] - 0x80) % 256 for s in range(500)}
    assert any(1 <= x <= ARITH_MAX for x in d) and any(x >= 256 - ARITH_MAX for x in d)


def test_different_pool_changes_sequence() -> None:
    def seq(pool: list[bytes]) -> list[bytes]:
        r = rng(3)
        return [mutate(b"seed" * 8, r, pool) for _ in range(100)]
    assert seq([b"x" * 32, b"y" * 32]) != seq([b"p" * 32, b"q" * 32])


def test_no_deterministic_stage() -> None:
    public = {k for k, v in vars(mutator).items()
              if callable(v) and not k.startswith("_") and getattr(v, "__module__", "") == mutator.__name__}
    assert public == {"bit_flip", "byte_flip", "arith", "interesting", "insert_bytes",
                      "delete_bytes", "havoc", "splice", "mutate"}
    assert not any("determin" in k or "walk" in k for k in vars(mutator))
