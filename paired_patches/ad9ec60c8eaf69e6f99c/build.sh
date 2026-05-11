#!/bin/sh
set -e
make allyesconfig
make -j `nproc` kernel/bpf/verifier.o net/core/filter.o include/linux/
