#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/ocfs2/alloc.o
