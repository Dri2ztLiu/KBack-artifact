#!/bin/sh
set -e
make allyesconfig
make -j `nproc` kernel/softirq.o
