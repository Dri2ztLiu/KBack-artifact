#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/fscache/volume.o include/linux/
