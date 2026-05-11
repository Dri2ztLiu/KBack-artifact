#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/udf/ialloc.o
