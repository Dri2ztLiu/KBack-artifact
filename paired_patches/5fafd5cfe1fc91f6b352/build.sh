#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/netrom/nr_timer.o
