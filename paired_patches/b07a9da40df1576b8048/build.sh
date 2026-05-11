#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/openvswitch/flow_netlink.o
