#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/gfs2/util.o
