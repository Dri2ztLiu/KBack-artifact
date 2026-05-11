#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/dcache.o
