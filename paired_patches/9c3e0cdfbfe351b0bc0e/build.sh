#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/btrfs/ref-verify.o
