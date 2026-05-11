#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/dma-buf/sync_debug.o
