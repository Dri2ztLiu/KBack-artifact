#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/bridge/br_multicast.o
