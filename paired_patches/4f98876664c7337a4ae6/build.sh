#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/bpf/test_run.o
