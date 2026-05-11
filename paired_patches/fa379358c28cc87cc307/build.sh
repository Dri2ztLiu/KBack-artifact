#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/unix/garbage.o include/net/
