#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/ntfs/inode.o
