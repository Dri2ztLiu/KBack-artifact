#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/hfsplus/inode.o
