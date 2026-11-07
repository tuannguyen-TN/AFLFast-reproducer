"""Shared test helpers. [AFL-003 needs_clang alignment]"""
import shutil
from pathlib import Path

import pytest

# Same preference order as targets/Makefile: Homebrew LLVM first, else clang on PATH.
HAVE_CLANG = Path("/opt/homebrew/opt/llvm/bin/clang").exists() or shutil.which("clang") is not None
needs_clang = pytest.mark.skipif(not HAVE_CLANG, reason="clang unavailable")
