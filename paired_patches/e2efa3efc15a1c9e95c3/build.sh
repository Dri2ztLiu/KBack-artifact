#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/ext4/balloc.o fs/ext4/ialloc.o fs/ext4/mballoc.o fs/ext4/super.o fs/ext4/
