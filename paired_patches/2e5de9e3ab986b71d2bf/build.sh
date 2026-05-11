#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/netdevsim/udp_tunnels.o drivers/net/netdevsim/
