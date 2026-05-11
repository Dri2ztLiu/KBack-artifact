#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/hfs/inode.o
