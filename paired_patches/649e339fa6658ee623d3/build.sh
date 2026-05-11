#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/netfilter/nft_ct.o
