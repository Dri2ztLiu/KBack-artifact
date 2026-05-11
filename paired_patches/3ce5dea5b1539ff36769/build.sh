#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/fat/nfs.o
