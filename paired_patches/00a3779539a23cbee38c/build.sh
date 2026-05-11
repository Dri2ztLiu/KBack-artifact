#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/reiserfs/xattr_security.o
