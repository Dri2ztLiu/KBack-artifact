#!/bin/sh
set -e
make allyesconfig
make -j `nproc` kernel/sched/fair.o kernel/sched/
