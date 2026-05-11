#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/netfilter/nf_conncount.o
