#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/802/mrp.o include/net/
