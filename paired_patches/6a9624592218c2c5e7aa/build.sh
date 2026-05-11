#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/vxlan/vxlan_core.o
