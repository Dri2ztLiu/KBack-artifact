#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/io_uring.o
