#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/ipv4/netfilter/nf_tproxy_ipv4.o
