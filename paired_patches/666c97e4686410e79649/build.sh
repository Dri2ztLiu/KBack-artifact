#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/netrom/af_netrom.o
