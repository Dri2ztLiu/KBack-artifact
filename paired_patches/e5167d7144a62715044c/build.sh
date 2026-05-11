#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/ipv4/inet_fragment.o net/ipv4/ip_fragment.o net/ipv6/netfilter/nf_conntrack_reasm.o include/linux/
