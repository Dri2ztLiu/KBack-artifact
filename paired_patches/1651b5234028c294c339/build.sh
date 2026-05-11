#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/netfilter/ipvs/ip_vs_conn.o net/netfilter/ipvs/ip_vs_core.o net/netfilter/ipvs/ip_vs_ctl.o net/netfilter/ipvs/ip_vs_est.o
