# Build instrumented fuzz targets. Requires clang.
# Instrumentation: SanitizerCoverage edge guards + AddressSanitizer.
CC      ?= clang
CFLAGS  ?= -O1 -g -fsanitize=address -fsanitize-coverage=trace-pc-guard
BIN      = bin

TARGETS = $(BIN)/toy_parser $(BIN)/tlv_parser

all: $(TARGETS)

$(BIN):
	mkdir -p $(BIN)

$(BIN)/%: %.c | $(BIN)
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -rf $(BIN)

.PHONY: all clean
