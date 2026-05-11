#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/bridge/netfilter/ebtables.o net/ipv4/netfilter/ip_tables.o net/ipv6/netfilter/ip6_tables.o
