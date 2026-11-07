# Build instrumented fuzz targets. Requires clang.
# Instrumentation: SanitizerCoverage edge guards + AddressSanitizer.
# Prefer Homebrew LLVM if present (Apple clang ASan hangs on macOS 26.x, ADR-0001), else `clang`; `make CC=...` overrides.
ifeq ($(origin CC),default)
CC = $(firstword $(wildcard /opt/homebrew/opt/llvm/bin/clang) clang)
endif
CFLAGS  ?= -O1 -g -fsanitize=address -fsanitize-coverage=trace-pc-guard
BIN      = bin

TARGETS = $(BIN)/toy_parser $(BIN)/tlv_parser $(BIN)/spike

all: $(TARGETS)

$(BIN):
	mkdir -p $(BIN)

$(BIN)/%: %.c | $(BIN)
	$(CC) $(CFLAGS) -o $@ $<

# AFL-001: coverage runtime (cov_rt.c) is linked into the spike target.
$(BIN)/spike: spike.c cov_rt.c | $(BIN)
	$(CC) $(CFLAGS) -O0 -o $@ spike.c cov_rt.c

clean:
	rm -rf $(BIN)

.PHONY: all clean
