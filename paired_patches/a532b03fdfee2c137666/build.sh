#!/bin/sh
set -e
make allyesconfig
make -j `nproc` block/blk-map.o
