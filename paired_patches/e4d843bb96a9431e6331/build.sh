#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/mptcp/pm_netlink.o
