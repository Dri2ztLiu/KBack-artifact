#!/bin/sh
set -e
make allyesconfig
make -j `nproc` kernel/power/hibernate.o
