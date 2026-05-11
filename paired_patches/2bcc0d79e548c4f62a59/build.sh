#!/bin/sh
set -e
make allyesconfig
make -j `nproc` block/genhd.o
