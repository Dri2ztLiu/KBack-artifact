#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/ethtool/strset.o
