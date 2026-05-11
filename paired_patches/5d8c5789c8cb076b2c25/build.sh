#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/netfilter/nf_tables_api.o net/netfilter/nft_compat.o include/net/netfilter/
