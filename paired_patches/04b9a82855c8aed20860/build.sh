#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/netfilter/ipvs/ip_vs_xmit.o
