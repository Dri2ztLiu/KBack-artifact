#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/squashfs/block.o
