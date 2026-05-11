#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/netfilter/xt_CHECKSUM.o net/netfilter/xt_CLASSIFY.o net/netfilter/xt_CONNSECMARK.o net/netfilter/xt_CT.o net/netfilter/xt_IDLETIMER.o net/netfilter/xt_LED.o net/netfilter/xt_NFLOG.o net/netfilter/xt_RATEEST.o net/netfilter/xt_SECMARK.o net/netfilter/xt_TRACE.o net/netfilter/xt_addrtype.o net/netfilter/xt_cluster.o net/netfilter/xt_connbytes.o net/netfilter/xt_connlimit.o net/netfilter/xt_connmark.o net/netfilter/xt_mark.o
