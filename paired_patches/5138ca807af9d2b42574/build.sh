#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/tipc/netlink.o
