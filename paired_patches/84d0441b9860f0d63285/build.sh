#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/netfilter/nft_inner.o include/net/netfilter/
