#!/bin/sh
set -e
make allyesconfig
make -j `nproc` kernel/trace/bpf_trace.o
