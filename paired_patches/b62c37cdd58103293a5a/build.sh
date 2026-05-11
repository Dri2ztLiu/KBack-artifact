#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/netfilter/ipset/ip_set_core.o
