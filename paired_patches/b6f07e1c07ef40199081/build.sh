#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/netfilter/nf_flow_table_inet.o net/netfilter/nf_flow_table_ip.o include/net/netfilter/
