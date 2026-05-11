#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/tipc/netlink_compat.o
