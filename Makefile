CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -D_GNU_SOURCE

.PHONY: all test clean

all: nvme-sentinel-probe

nvme-sentinel-probe: src/native/nvme_probe.c
	$(CC) $(CFLAGS) -o $@ $<

test: all
	/usr/bin/python3 -m py_compile src/nvme_sentinel/*.py
	./nvme-sentinel-probe --sample-ms 80 --json >/dev/null
	PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v

clean:
	rm -f nvme-sentinel-probe
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
