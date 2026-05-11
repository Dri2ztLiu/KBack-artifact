#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/io-wq.o
