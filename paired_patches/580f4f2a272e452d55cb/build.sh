#!/bin/sh
set -e
make allyesconfig
make -j `nproc` kernel/bpf/bpf_iter.o
