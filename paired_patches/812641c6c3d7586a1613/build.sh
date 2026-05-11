#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/isofs/dir.o
