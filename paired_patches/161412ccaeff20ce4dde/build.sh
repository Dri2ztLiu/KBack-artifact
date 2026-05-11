#!/bin/sh
set -e
make allyesconfig
make -j `nproc` kernel/trace/trace.o
