#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/ext4/inline.o
