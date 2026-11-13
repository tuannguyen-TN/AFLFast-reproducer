# Build instrumented fuzz targets. Requires clang.
# Instrumentation: SanitizerCoverage edge guards + AddressSanitizer.
# Prefer Homebrew LLVM if present (Apple clang ASan hangs on macOS 26.x, ADR-0001), else `clang`; `make CC=...` overrides.
ifeq ($(origin CC),default)
CC = $(firstword $(wildcard /opt/homebrew/opt/llvm/bin/clang) clang)
endif
# User CFLAGS may add extras; REQUIRED_FLAGS come last (so -O0 wins) and cannot be overridden by env/CLI
# (`override` also beats `make REQUIRED_FLAGS=...`). Targets are all built by the pattern rule below.
CFLAGS  ?= -g
override REQUIRED_FLAGS = -O0 -fno-omit-frame-pointer -fsanitize=address -fsanitize-coverage=trace-pc-guard
BIN      = bin

TARGETS = $(BIN)/toy_parser $(BIN)/tlv_parser $(BIN)/spike

all: $(TARGETS)

$(BIN):
	mkdir -p $(BIN)

# AFL-002: every fuzz target links the coverage runtime (cov_rt.c).
$(BIN)/%: %.c cov_rt.c | $(BIN)
	$(CC) $(CFLAGS) $(REQUIRED_FLAGS) -o $@ $< cov_rt.c

clean:
	rm -rf $(BIN)

.PHONY: all clean
