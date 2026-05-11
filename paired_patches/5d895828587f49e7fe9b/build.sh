#!/bin/sh
set -e
make allyesconfig
make -j `nproc` kernel/bpf/ringbuf.o
