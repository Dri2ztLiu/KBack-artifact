#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/fuse/dev.o
