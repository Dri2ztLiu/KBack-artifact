#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/btrfs/free-space-tree.o fs/btrfs/
