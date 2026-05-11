#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/f2fs/namei.o fs/f2fs/ include/linux/
