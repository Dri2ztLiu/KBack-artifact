#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/nfs/inode.o
