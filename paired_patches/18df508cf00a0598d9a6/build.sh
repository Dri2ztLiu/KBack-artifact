#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/buffer.o fs/ext4/inode.o
