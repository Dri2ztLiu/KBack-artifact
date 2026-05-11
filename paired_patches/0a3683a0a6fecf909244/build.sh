#!/bin/sh
set -e
make allyesconfig
make -j `nproc` block/fops.o
