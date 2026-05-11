#!/bin/sh
set -e
make allyesconfig
make -j `nproc` kernel/fork.o
