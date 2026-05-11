#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/netlink/af_netlink.o
