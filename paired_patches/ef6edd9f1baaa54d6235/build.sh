#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/ethtool/ioctl.o
