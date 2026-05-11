#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/fhandle.o
