#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/tap.o drivers/net/tun.o net/sched/sch_generic.o include/linux/
