#!/bin/sh
set -e
make allyesconfig
make -j `nproc` kernel/cgroup/legacy_freezer.o
