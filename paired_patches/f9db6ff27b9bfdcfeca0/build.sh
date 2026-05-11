#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/rds/recv.o
