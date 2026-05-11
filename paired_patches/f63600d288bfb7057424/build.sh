#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/sched/sch_cake.o
