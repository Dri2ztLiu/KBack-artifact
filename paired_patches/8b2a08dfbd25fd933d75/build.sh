#!/bin/sh
set -e
make allyesconfig
make -j `nproc` kernel/bpf/log.o
