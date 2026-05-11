#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/exec.o fs/proc/base.o init/init_task.o kernel/events/core.o kernel/fork.o kernel/kcmp.o kernel/pid.o include/linux/sched/
