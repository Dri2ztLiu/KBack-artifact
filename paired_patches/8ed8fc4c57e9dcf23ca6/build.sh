#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/sched/act_pedit.o
