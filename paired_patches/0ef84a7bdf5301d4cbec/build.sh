#!/bin/sh
set -e
make allyesconfig
make -j `nproc` kernel/bpf/cgroup.o net/core/filter.o
