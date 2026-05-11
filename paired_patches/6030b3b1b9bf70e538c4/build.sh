#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/hfsplus/bfind.o fs/hfsplus/extents.o fs/hfsplus/
