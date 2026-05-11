#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/netfs/buffered_read.o
