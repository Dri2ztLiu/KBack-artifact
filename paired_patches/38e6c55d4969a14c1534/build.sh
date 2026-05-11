#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/block/nbd.o
