#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/ipv6/ip6_offload.o include/linux/
