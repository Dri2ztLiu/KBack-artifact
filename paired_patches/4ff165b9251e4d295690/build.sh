#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/netfilter/xt_nfacct.o
