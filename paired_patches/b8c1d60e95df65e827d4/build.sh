#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/f2fs/extent_cache.o
