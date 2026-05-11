#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/9p/vfs_inode.o
