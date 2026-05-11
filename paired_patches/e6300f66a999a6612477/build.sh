#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/hamradio/bpqether.o
