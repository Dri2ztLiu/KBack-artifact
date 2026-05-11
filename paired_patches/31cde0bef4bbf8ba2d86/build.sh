#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/openvswitch/datapath.o
