#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/xdp/xsk_queue.o
