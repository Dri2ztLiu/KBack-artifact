#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/hfs/mdb.o
