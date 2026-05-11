#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/proc/base.o fs/proc/task_mmu.o fs/proc/task_nommu.o
