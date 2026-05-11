#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/md/md.o
