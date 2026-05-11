#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/btrfs/ordered-data.o
