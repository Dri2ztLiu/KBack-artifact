#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/sched/cls_flow.o
