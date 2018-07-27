# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SHELL := bash
VERSION := 0.0.2
CC := armv7a-cros-linux-gnueabi-gcc
CFLAGS := -g -Wall -O2 -Wl,--no-experimental-use-relr
INCLUDES := -Iinclude
DESTDIR := /usr/bin
BINDIR := ./bin
SRCDIR := ./src
DISTDIR := ./dist
CONFDIR := /etc/init
INITDIR := ./deploy/init
EGGDIR := ./chameleond.egg-info
STREAM_SRCS = $(wildcard $(SRCDIR)/stream_server/*.c)
STREAM_OBJS = $(patsubst $(SRCDIR)/stream_server/*.c,$(BINDIR)/%.o,$(STREAM_SRCS))
CONFFILES = chameleond.conf
IDENTITY_FILE := ~/trunk/src/scripts/mod_for_test_scripts/ssh_keys/testing_rsa

TARGETS = directories chameleond

.PHONY: all
all: $(TARGETS)

.PHONY: directories
directories:
	@mkdir -p $(BINDIR)

BINARIES = $(BINDIR)/histogram $(BINDIR)/hpd_control $(BINDIR)/pixeldump \
	  $(BINDIR)/avsync $(BINDIR)/stream_server $(BINDIR)/printer

.PHONY: binaries
binaries: $(BINARIES)

.PHONY: chameleond
chameleond: binaries
	@python setup.py sdist

$(BINDIR)/%.o: $(SRCDIR)/%.c
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

$(BINDIR)/%: $(BINDIR)/%.o
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^

$(BINDIR)/stream_server.o: $(SRCDIR)/stream_server/%.c
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

$(BINDIR)/stream_server: $(STREAM_OBJS)
	$(CC) $(CFLAGS) -lpthread $(INCLUDES) -o $@ $^


BUNDLE_VERSION ?= '9999'
CHAMELEON_BOARD ?= 'fpga_tio'
# Get current time from the host.
HOST_NOW := `date "+%Y-%m-%d %H:%M:%S"`

# Check if this is a Chrome OS platform.
# The '$' symbol in awk has to be doubled in Makefile.
PLATFORM = $(shell awk -F= '/CHROMEOS_RELEASE_NAME/ {print $$2}' \
	     /etc/lsb-release 2>/dev/null)

.PHONY: install
install:
	@mkdir -p $(DESTDIR)
	@cp -f $(BINARIES) "$(DESTDIR)"
ifeq ($(REMOTE_INSTALL), TRUE)
	@echo sync time with host...
	@NOW="$(HOST_NOW)" deploy/deploy_pip
else
	@echo sync time with the chameleon mirror server...
	@NOW="`chameleond/utils/server_time`" deploy/deploy_pip
endif
	@python setup.py install -f

ifeq ($(PLATFORM), Chrome OS)
	@cp -f $(INITDIR)/$(CONFFILES) $(CONFDIR)
	@echo Installing chameleon package on chrome os platform is completed.
	@echo Please do \"\$ start chameleond\" or \"\$ restart chameleond\".
else
	@BUNDLE_VERSION=$(BUNDLE_VERSION) CHAMELEON_BOARD=$(CHAMELEON_BOARD) \
	deploy/deploy
	@echo Installing chameleon package on fpga platform is completed.
endif

CHAMELEON_USER ?= root
BUNDLE = chameleond-$(VERSION).tar.gz
BUNDLEDIR = chameleond-$(VERSION)

.PHONY: remote-install
remote-install:
	@echo "Set bundle version to $(BUNDLE_VERSION)"
	@echo "Set board to $(CHAMELEON_BOARD)"
	@echo "Current host time: $(HOST_NOW)"
ifdef CHAMELEON_HOST
	@scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
	    -i $(IDENTITY_FILE) \
	    $(DISTDIR)/$(BUNDLE) $(CHAMELEON_USER)@$(CHAMELEON_HOST):/tmp
	@ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
	    -i $(IDENTITY_FILE) \
	    $(CHAMELEON_USER)@$(CHAMELEON_HOST) \
	    "cd /tmp && rm -rf $(BUNDLEDIR) && tar zxf $(BUNDLE) &&" \
	    "cd $(BUNDLEDIR) && find -exec touch -c {} \; &&" \
	    "make install " \
	        "REMOTE_INSTALL=TRUE" \
	        "HOST_NOW=\"$(HOST_NOW)\"" \
	        "BUNDLE_VERSION=$(BUNDLE_VERSION) " \
	        "CHAMELEON_BOARD=$(CHAMELEON_BOARD)"
else
	$(error CHAMELEON_HOST is undefined)
endif

.PHONY: clean
clean:
	@rm -rf $(BINDIR) $(DISTDIR) $(EGGDIR)

PYLINTRC = $(CROS_WORKON_SRCROOT)/chromite/pylintrc
PYLINT_OPTIONS = \
	--rcfile=$(PYLINTRC) \
	--disable=R0921,R0922,R0923,R9100,cros-logging-import

LINT_FILES = $(shell find -name '*.py' -type f | sort)
LINT_BLACKLIST =
LINT_WHITELIST = $(filter-out $(LINT_BLACKLIST),$(LINT_FILES))

lint:
	@set -e -o pipefail; \
	out=$$(mktemp); \
	echo Linting $(shell echo $(LINT_WHITELIST) | wc -w) files...; \
	if [ -n "$(LINT_WHITELIST)" ] && \
	    ! env \
	    PYTHONPATH=.:chameleond:../chameleon-private:../video-chameleon \
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
