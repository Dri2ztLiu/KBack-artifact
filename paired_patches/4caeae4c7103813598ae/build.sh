#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/sched/ematch.o
