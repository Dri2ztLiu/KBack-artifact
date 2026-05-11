#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/9p/trans_fd.o
