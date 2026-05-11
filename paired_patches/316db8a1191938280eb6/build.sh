#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/overlayfs/copy_up.o
