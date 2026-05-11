#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/xfs/xfs_filestream.o fs/xfs/
