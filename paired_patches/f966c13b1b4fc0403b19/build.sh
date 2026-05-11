#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/erofs/inode.o
