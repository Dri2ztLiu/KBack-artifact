#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/sched/sch_choke.o net/sched/sch_gred.o net/sched/sch_red.o net/sched/sch_sfq.o include/net/
