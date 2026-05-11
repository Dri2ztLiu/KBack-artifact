#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/hamradio/6pack.o
