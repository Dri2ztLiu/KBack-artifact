#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/f2fs/checkpoint.o fs/f2fs/super.o fs/f2fs/
