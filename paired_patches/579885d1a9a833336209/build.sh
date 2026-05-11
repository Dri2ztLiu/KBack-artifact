#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/overlayfs/file.o
