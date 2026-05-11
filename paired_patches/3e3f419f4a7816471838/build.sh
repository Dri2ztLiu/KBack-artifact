#!/bin/sh
set -e
make allyesconfig
make -j `nproc` block/blk-core.o block/genhd.o
