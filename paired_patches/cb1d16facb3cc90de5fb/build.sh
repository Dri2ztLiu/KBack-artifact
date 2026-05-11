#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/9p/xattr.o
