#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/ipv6/xfrm6_tunnel.o net/xfrm/xfrm_state.o
