#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/ipvlan/ipvlan_core.o
