PY      := python3
AS      := as
LD      := ld
EXDIR   := examples
BUILD   := build

BF_SOURCES := $(wildcard $(EXDIR)/*.bf)
BINARIES   := $(patsubst $(EXDIR)/%.bf,$(BUILD)/%,$(BF_SOURCES))

.PHONY: all clean test

all: $(BINARIES)

$(BUILD)/%.s: $(EXDIR)/%.bf | $(BUILD)
	$(PY) -m bf2asm $< -o $@

$(BUILD)/%.o: $(BUILD)/%.s
	$(AS) -o $@ $<

$(BUILD)/%: $(BUILD)/%.o
	$(LD) -o $@ $<

$(BUILD):
	mkdir -p $(BUILD)

test:
	$(PY) -m unittest discover -v

clean:
	rm -rf $(BUILD)
