#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/f2fs/file.o fs/f2fs/super.o fs/f2fs/
