#!/bin/sh
set -e
make allyesconfig
make -j `nproc` kernel/events/core.o
