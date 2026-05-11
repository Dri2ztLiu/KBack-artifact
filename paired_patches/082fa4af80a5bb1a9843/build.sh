#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/squashfs/xattr_id.o
