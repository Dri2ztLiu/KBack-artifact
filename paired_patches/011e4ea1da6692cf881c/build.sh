#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/pipe.o
