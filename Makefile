# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SHELL := bash
CC := armv7a-cros-linux-gnueabi-gcc
CFLAGS := -g -Wall
INCLUDES := -Iinclude
DESTDIR := /usr/bin
BINDIR := ./bin
SRCDIR := ./src

TARGETS = directories binaries

.PHONY: all
all: $(TARGETS)

.PHONY: directories
directories:
	@mkdir -p $(BINDIR)

BINARIES = $(BINDIR)/hpd_control

.PHONY: binaries
binaries: $(BINARIES)

$(BINDIR)/hpd_control.o: $(SRCDIR)/hpd_control.c
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

$(BINDIR)/hpd_control: $(BINDIR)/hpd_control.o
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^

.PHONY: install
install:
	@mkdir -p $(DESTDIR)
	@cp -f $(BINARIES) "$(DESTDIR)"

.PHONY: clean
clean:
	@rm -rf $(BINDIR)

PYLINTRC = $(CROS_WORKON_SRCROOT)/chromite/pylintrc
PYLINT_OPTIONS = \
	--rcfile=$(PYLINTRC) \
	--disable=R0921,R0922

LINT_FILES = $(shell find -name '*.py' -type f | sort)
LINT_BLACKLIST =
LINT_WHITELIST = $(filter-out $(LINT_BLACKLIST),$(LINT_FILES))

lint:
	@set -e -o pipefail; \
	out=$$(mktemp); \
	echo Linting $(shell echo $(LINT_WHITELIST) | wc -w) files...; \
	if [ -n "$(LINT_WHITELIST)" ] && \
	    ! env \
	    PYTHONPATH=.:../chameleon-private:../video-chameleon \
	    pylint $(PYLINT_OPTIONS) $(LINT_WHITELIST) \
	    |& tee $$out; then \
	  echo; \
	  echo To re-lint failed files, run:; \
	  echo make lint LINT_WHITELIST=\""$$( \
	    grep '^\*' $$out | cut -c22- | tr . / | \
	    sed 's/$$/.py/' | tr '\n' ' ' | sed -e 's/ $$//')"\"; \
	  echo; \
	  rm -f $$out; \
	  exit 1; \
	fi; \
	echo ...no lint errors! You are awesome!; \
	rm -f $$out

PRESUBMIT_FILES := $(if $(PRESUBMIT_FILES),\
	             $(shell realpath --relative-to=. $$PRESUBMIT_FILES))

lint-presubmit:
	$(MAKE) lint \
	    LINT_FILES="$(filter %.py,$(PRESUBMIT_FILES))" \
	    2>/dev/null

chroot-presubmit:
	if [ ! -e /etc/debian_chroot ]; then \
	    echo "This script must be run inside the chroot. Run this first:"; \
	    echo "    cros_sdk"; \
	    exit 1; \
	fi
