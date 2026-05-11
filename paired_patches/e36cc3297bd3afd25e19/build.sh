#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/ntfs3/inode.o
