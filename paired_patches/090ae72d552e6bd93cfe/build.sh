#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/xfs/xfs_fsmap.o
