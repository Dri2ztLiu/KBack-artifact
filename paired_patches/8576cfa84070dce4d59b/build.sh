#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/btrfs/tree-log.o
