#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/ext2/super.o fs/ext2/
