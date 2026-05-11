#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/hfs/super.o
