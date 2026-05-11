#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/unix/af_unix.o
