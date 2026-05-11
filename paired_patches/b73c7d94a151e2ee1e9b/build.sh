#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/netfs/buffered_write.o
