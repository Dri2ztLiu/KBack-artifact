#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/jfs/file.o
