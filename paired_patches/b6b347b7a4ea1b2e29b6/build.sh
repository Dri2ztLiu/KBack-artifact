#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/f2fs/inode.o fs/f2fs/
