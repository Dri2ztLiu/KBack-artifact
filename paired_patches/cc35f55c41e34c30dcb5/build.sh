#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/btrfs/extent_io.o
