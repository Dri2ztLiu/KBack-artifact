#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/hfsplus/xattr.o
