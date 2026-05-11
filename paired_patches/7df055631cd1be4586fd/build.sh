#!/bin/sh
set -e
make allyesconfig
make -j `nproc` io_uring/cancel.o
