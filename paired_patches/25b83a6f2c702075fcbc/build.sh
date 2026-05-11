#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/netfs/write_collect.o
