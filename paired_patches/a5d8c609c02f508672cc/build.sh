#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/block/loop.o
