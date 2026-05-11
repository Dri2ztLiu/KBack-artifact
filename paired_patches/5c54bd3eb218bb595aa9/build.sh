#!/bin/sh
set -e
make allyesconfig
make -j `nproc` kernel/time/posix-timers.o include/linux/sched/
